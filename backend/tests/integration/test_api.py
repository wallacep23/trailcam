"""HTTP API against a real database (DESIGN §15)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from trailcam.api.main import create_app
from trailcam.config import Settings
from trailcam.pipeline import jobs

pytestmark = pytest.mark.integration


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None), configure_logs=False)
    with TestClient(app) as c:
        yield c


def test_health_reports_db_extensions_and_schema(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok", body
    checks = {c["name"]: c["ok"] for c in body["checks"]}
    assert checks == {
        "database": True,
        "extension:postgis": True,
        "extension:vector": True,
        "schema": True,
    }
    assert body["schema_revision"] == body["schema_head"] == "0001"


def test_request_id_is_echoed(client: TestClient) -> None:
    res = client.get("/api/v1/health", headers={"x-request-id": "abc123"})
    assert res.headers["x-request-id"] == "abc123"
    assert client.get("/api/v1/health").headers["x-request-id"]


def test_create_list_get_job(client: TestClient) -> None:
    res = client.post("/api/v1/jobs", json={"type": "system.selftest", "payload": {"steps": 2}})
    assert res.status_code == 201, res.text
    job = res.json()
    assert job["status"] == "queued"
    assert job["payload"] == {"steps": 2}
    assert job["max_attempts"] == 3

    listing = client.get("/api/v1/jobs", params={"status": "queued"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == job["id"]
    assert client.get("/api/v1/jobs", params={"status": "failed"}).json()["total"] == 0
    assert client.get(f"/api/v1/jobs/{job['id']}").json()["id"] == job["id"]
    stats = client.get("/api/v1/jobs/stats").json()["counts"]
    assert stats["queued"] == 1
    assert stats["failed"] == 0


def test_job_types_and_validation(client: TestClient) -> None:
    types = {t["type"]: t for t in client.get("/api/v1/jobs/types").json()}
    assert types["system.selftest"]["user_runnable"] is True
    assert client.post("/api/v1/jobs", json={"type": "nope"}).status_code == 400
    assert client.post("/api/v1/jobs", json={}).status_code == 422
    missing = "01890000-0000-7000-8000-000000000000"
    assert client.get(f"/api/v1/jobs/{missing}").status_code == 404
    assert client.post(f"/api/v1/jobs/{missing}/retry").status_code == 404


def test_retry_failed_job_via_api(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as s:
        job = jobs.enqueue(s, "system.selftest", max_attempts=1).job
        s.commit()
        assert client.post(f"/api/v1/jobs/{job.id}/retry").status_code == 409  # still queued
        jobs.claim(s, "w")
        jobs.fail(s, job.id, "boom")
    res = client.post(f"/api/v1/jobs/{job.id}/retry")
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    assert res.json()["attempts"] == 0
    cancelled = client.post(f"/api/v1/jobs/{job.id}/cancel")
    assert cancelled.json()["status"] == "cancelled"


def test_properties_round_trip_geography(client: TestClient) -> None:
    body = {"name": "Judy's", "tz": "America/Detroit", "centroid": {"lat": 42.493, "lon": -83.665}}
    res = client.post("/api/v1/properties", json=body)
    assert res.status_code == 201, res.text
    prop = res.json()
    assert prop["centroid"] == {"lat": pytest.approx(42.493), "lon": pytest.approx(-83.665)}
    assert prop["has_boundary"] is False
    assert prop["site_count"] == 0
    assert client.get(f"/api/v1/properties/{prop['id']}").json()["name"] == "Judy's"
    assert [p["id"] for p in client.get("/api/v1/properties").json()] == [prop["id"]]
    assert client.post("/api/v1/properties", json=body).status_code == 409


def test_property_validation(client: TestClient) -> None:
    bad_tz = client.post("/api/v1/properties", json={"name": "x", "tz": "Mars/Olympus"})
    assert bad_tz.status_code == 422
    bad_lat = client.post(
        "/api/v1/properties", json={"name": "x", "tz": "UTC", "centroid": {"lat": 91, "lon": 0}}
    )
    assert bad_lat.status_code == 422
    no_centroid = client.post("/api/v1/properties", json={"name": "x", "tz": "UTC"})
    assert no_centroid.json()["centroid"] is None
