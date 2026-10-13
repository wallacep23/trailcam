"""Shared fixtures.

Unit tests need nothing. Integration tests (``@pytest.mark.integration``) need a PostgreSQL 16
database with PostGIS and pgvector available, given by ``TRAILCAM_TEST_DATABASE_URL``; they are
skipped when it is unset. The database is migrated to head once per session and every table is
truncated before each test. **Never point this at a database whose data you care about.**

    docker compose up -d db
    export TRAILCAM_TEST_DATABASE_URL=postgresql+psycopg://trailcam:trailcam@localhost:5432/trailcam_test
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DB_ENV = "TRAILCAM_TEST_DATABASE_URL"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(TEST_DB_ENV):
        return
    skip = pytest.mark.skip(reason=f"{TEST_DB_ENV} is not set")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Each test sees fresh settings built from its own environment."""
    from trailcam.config import get_settings
    from trailcam.db import session as db_session

    url = os.environ.get(TEST_DB_ENV)
    if url:
        monkeypatch.setenv("TRAILCAM_DATABASE_URL", url)
    monkeypatch.setenv("TRAILCAM_ENV", "test")
    monkeypatch.setenv("TRAILCAM_LOG_FORMAT", "console")
    get_settings.cache_clear()
    db_session.get_session_factory.cache_clear()
    yield
    get_settings.cache_clear()
    db_session.get_session_factory.cache_clear()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"{TEST_DB_ENV} is not set")
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    from alembic import command

    from trailcam.db import session as db_session
    from trailcam.db.migrate import alembic_config

    command.upgrade(alembic_config(database_url), "head")
    eng = db_session.make_engine(database_url, pool_size=10)
    # Route the app's cached engine to the test database for the whole session.
    db_session.get_engine.cache_clear()
    original = db_session.get_engine
    db_session.get_engine = lambda: eng  # type: ignore[assignment]
    yield eng
    db_session.get_engine = original
    eng.dispose()


def truncate_all(engine: Engine) -> None:
    from trailcam.db.models import ALL_TABLES

    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(ALL_TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    from trailcam.db.session import make_session_factory

    truncate_all(engine)
    yield make_session_factory(engine)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session
