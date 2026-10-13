"""Properties API (FR-SITE-1, minimal in M0: create, list, get)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from geoalchemy2 import Geometry
from geoalchemy2.elements import WKTElement
from sqlalchemy import Select, cast, func, select
from sqlalchemy.exc import IntegrityError

from trailcam.api.deps import DbSession
from trailcam.api.schemas import ErrorOut, LatLon, PropertyCreate, PropertyOut
from trailcam.db.models import Property, Site

router = APIRouter(prefix="/properties", tags=["properties"])


def _query() -> Select[Any]:
    geom = cast(Property.centroid, Geometry)
    site_count = (
        select(func.count(Site.id)).where(Site.property_id == Property.id).scalar_subquery()
    )
    return select(
        Property,
        func.ST_Y(geom).label("lat"),
        func.ST_X(geom).label("lon"),
        site_count.label("site_count"),
    )


def _out(row: Any) -> PropertyOut:
    prop: Property = row[0]
    centroid = LatLon(lat=row.lat, lon=row.lon) if row.lat is not None else None
    return PropertyOut(
        id=prop.id,
        name=prop.name,
        tz=prop.tz,
        centroid=centroid,
        has_boundary=prop.boundary is not None,
        site_count=row.site_count,
        created_at=prop.created_at,
    )


@router.get("", response_model=list[PropertyOut])
def list_properties(db: DbSession) -> list[PropertyOut]:
    return [_out(r) for r in db.execute(_query().order_by(Property.name))]


@router.post(
    "",
    response_model=PropertyOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorOut}},
)
def create_property(body: PropertyCreate, db: DbSession) -> PropertyOut:
    prop = Property(name=body.name, tz=body.tz)
    if body.centroid is not None:
        prop.centroid = WKTElement(f"POINT({body.centroid.lon} {body.centroid.lat})", srid=4326)
    db.add(prop)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"a property named {body.name!r} already exists"
        ) from exc
    return get_property(prop.id, db)


@router.get("/{property_id}", response_model=PropertyOut, responses={404: {"model": ErrorOut}})
def get_property(property_id: uuid.UUID, db: DbSession) -> PropertyOut:
    row = db.execute(_query().where(Property.id == property_id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"property {property_id} not found")
    return _out(row)
