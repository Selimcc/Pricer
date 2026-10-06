"""Requêtes géographiques PostGIS.

L'expression `store_geography()` est identique à celle de l'index GiST
`ix_stores_geog` (migration 0002) : PostgreSQL peut donc utiliser l'index
pour `ST_DWithin`.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Store


def point(latitude: float, longitude: float):
    return func.geography(func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326))


def store_geography():
    return func.geography(func.ST_SetSRID(func.ST_MakePoint(Store.longitude, Store.latitude), 4326))


def stores_within(db: Session, latitude: float, longitude: float, radius_km: float, limit: int = 200):
    """Magasins à moins de `radius_km`, du plus proche au plus loin -> [(Store, distance_km)]."""
    here = point(latitude, longitude)
    distance_m = func.ST_Distance(store_geography(), here)
    rows = db.execute(
        select(Store, distance_m.label("distance_m"))
        .where(func.ST_DWithin(store_geography(), here, radius_km * 1000))
        .order_by(distance_m)
        .limit(limit)
    ).all()
    return [(store, round(d / 1000, 2)) for store, d in rows]


def distance_km(db: Session, store: Store, latitude: float, longitude: float) -> float:
    d = db.scalar(select(func.ST_Distance(point(store.latitude, store.longitude), point(latitude, longitude))))
    return round(float(d) / 1000, 3)
