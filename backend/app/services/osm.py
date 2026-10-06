"""Magasins réels depuis OpenStreetMap (API Overpass, gratuite).

Import « paresseux » : la première fois qu'un utilisateur cherche autour
d'un point, on récupère les supermarchés de la zone et on les garde en
base. Les recherches suivantes dans la même zone ne rappellent pas Overpass.
Données © contributeurs OpenStreetMap, licence ODbL.
"""
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import OsmImportArea, Store
from app.services.scoring import haversine_km

SHOP_TYPES = ("supermarket", "convenience", "wholesale")
MIN_IMPORT_RADIUS_KM = 3.0
MAX_IMPORT_RADIUS_KM = 10.0
_FAILURE_BACKOFF_S = 300
_last_failure: dict[tuple[float, float], float] = {}


def _overpass_query(latitude: float, longitude: float, radius_km: float) -> str:
    shops = "|".join(SHOP_TYPES)
    r = int(radius_km * 1000)
    return (
        "[out:json][timeout:20];"
        f'nwr["shop"~"^({shops})$"](around:{r},{latitude},{longitude});'
        "out center tags;"
    )


def parse_overpass(payload: dict) -> list[dict]:
    stores = []
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        name = tags.get("name") or tags.get("brand")
        if lat is None or lon is None or not name:
            continue
        street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
        stores.append({
            "osm_type": el.get("type"),
            "osm_id": int(el["id"]),
            "name": name[:255],
            "chain": (tags.get("brand") or name)[:100],
            "address": street[:500] or None,
            "city": (tags.get("addr:city") or None),
            "postcode": (tags.get("addr:postcode") or None),
            "latitude": float(lat),
            "longitude": float(lon),
            "shop_type": tags.get("shop"),
            "source": "osm",
        })
    return stores


def upsert_osm_stores(db: Session, stores: list[dict]) -> int:
    # Une même ligne deux fois dans un ON CONFLICT ferait échouer la requête
    stores = list({(s["osm_type"], s["osm_id"]): s for s in stores}.values())
    if not stores:
        return 0
    stmt = insert(Store).values(stores)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_stores_osm",
        set_={
            "name": stmt.excluded.name,
            "chain": stmt.excluded.chain,
            "address": stmt.excluded.address,
            "city": stmt.excluded.city,
            "postcode": stmt.excluded.postcode,
            "latitude": stmt.excluded.latitude,
            "longitude": stmt.excluded.longitude,
            "shop_type": stmt.excluded.shop_type,
        },
    )
    db.execute(stmt)
    return len(stores)


def get_or_create_osm_store(db: Session, data: dict) -> Store:
    store = db.scalar(select(Store).where(Store.osm_type == data["osm_type"], Store.osm_id == data["osm_id"]))
    if store:
        return store
    upsert_osm_stores(db, [data])
    return db.scalar(select(Store).where(Store.osm_type == data["osm_type"], Store.osm_id == data["osm_id"]))


def fetch_overpass(latitude: float, longitude: float, radius_km: float) -> list[dict] | None:
    try:
        response = httpx.post(
            settings.overpass_url,
            data={"data": _overpass_query(latitude, longitude, radius_km)},
            headers={"User-Agent": settings.http_user_agent},
            timeout=25.0,
        )
        response.raise_for_status()
        return parse_overpass(response.json())
    except Exception as exc:  # réseau, quota Overpass, JSON invalide…
        print(f"[osm] import impossible : {exc}")
        return None


def area_is_covered(db: Session, latitude: float, longitude: float, radius_km: float) -> bool:
    since = datetime.now(timezone.utc) - timedelta(days=settings.osm_area_refresh_days)
    areas = db.scalars(select(OsmImportArea).where(OsmImportArea.imported_at >= since)).all()
    for area in areas:
        d = haversine_km(latitude, longitude, area.latitude, area.longitude)
        if d is not None and d + radius_km <= area.radius_km + 0.01:
            return True
    return False


def ensure_area_imported(db: Session, latitude: float, longitude: float, radius_km: float) -> int | None:
    """Importe les magasins OSM autour du point si la zone n'est pas déjà connue.

    Retourne le nombre de magasins importés, 0 si la zone était déjà couverte,
    None si l'import a échoué (l'application continue avec ce qu'elle a).
    """
    if not settings.enable_osm_import:
        return 0
    radius = min(max(radius_km, MIN_IMPORT_RADIUS_KM), MAX_IMPORT_RADIUS_KM)
    if area_is_covered(db, latitude, longitude, min(radius_km, MAX_IMPORT_RADIUS_KM)):
        return 0

    key = (round(latitude, 2), round(longitude, 2))
    if time.monotonic() - _last_failure.get(key, -1e9) < _FAILURE_BACKOFF_S:
        return None

    stores = fetch_overpass(latitude, longitude, radius)
    if stores is None:
        _last_failure[key] = time.monotonic()
        return None

    count = upsert_osm_stores(db, stores)
    db.add(OsmImportArea(latitude=latitude, longitude=longitude, radius_km=radius, store_count=count))
    db.commit()
    return count
