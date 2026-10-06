from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models import PriceObservation, Product, Store
from app.routers.deps import api_error
from app.services import geo, osm, pricing

router = APIRouter(prefix="/stores", tags=["Magasins"])


def store_out(store: Store, distance_km: float | None = None, price_count: int | None = None,
              last_price_at=None) -> dict:
    return {
        "id": store.id,
        "chain": store.chain,
        "name": store.name,
        "address": store.address,
        "city": store.city,
        "postcode": store.postcode,
        "latitude": store.latitude,
        "longitude": store.longitude,
        "shop_type": store.shop_type,
        "source": store.source,
        "distance_km": distance_km,
        "price_count": price_count,
        "last_price_at": last_price_at,
    }


@router.get("")
def list_stores(limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    return [store_out(s) for s in db.scalars(select(Store).order_by(Store.chain, Store.name).limit(limit)).all()]


@router.get("/nearby")
def nearby_stores(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(5, gt=0, le=50),
    limit: int = Query(60, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Magasins autour du point (importés d'OpenStreetMap à la première visite de la zone)."""
    osm.ensure_area_imported(db, latitude, longitude, radius_km)
    stores = geo.stores_within(db, latitude, longitude, radius_km, limit)
    since = datetime.now(timezone.utc) - timedelta(days=settings.price_max_age_days)
    counts = {}
    if stores:
        counts = {
            sid: (n, last) for sid, n, last in db.execute(
                select(PriceObservation.store_id, func.count(), func.max(PriceObservation.observed_at))
                .where(PriceObservation.store_id.in_([s.id for s, _ in stores]), PriceObservation.observed_at >= since)
                .group_by(PriceObservation.store_id)
            ).all()
        }
    return [store_out(s, d, *counts.get(s.id, (0, None))) for s, d in stores]


@router.get("/{store_id}")
def store_detail(store_id: int, latitude: float | None = None, longitude: float | None = None,
                 db: Session = Depends(get_db)):
    """Fiche magasin et derniers prix relevés dans ce magasin."""
    store = db.get(Store, store_id)
    if not store:
        raise api_error(404, "store_not_found", "Magasin introuvable.")
    distance = geo.distance_km(db, store, latitude, longitude) if latitude is not None and longitude is not None else None
    since = datetime.now(timezone.utc) - timedelta(days=settings.price_max_age_days)
    product_ids = db.scalars(
        select(PriceObservation.product_id)
        .where(PriceObservation.store_id == store.id, PriceObservation.observed_at >= since)
        .group_by(PriceObservation.product_id)
        .order_by(func.max(PriceObservation.observed_at).desc())
        .limit(50)
    ).all()
    products = db.scalars(select(Product).where(Product.id.in_(product_ids))).all() if product_ids else []
    rows = pricing.current_prices(db, list(products), [(store, distance)])
    product_by_id = {p.id: p for p in products}
    prices = sorted(
        ({**row, "product": {"ean": product_by_id[pid].ean, "name": product_by_id[pid].name,
                             "brand": product_by_id[pid].brand, "image_url": product_by_id[pid].image_url,
                             "quantity": product_by_id[pid].quantity}}
         for (pid, _), row in rows.items()),
        key=lambda r: r["observed_at"], reverse=True,
    )
    return {"store": store_out(store, distance, len(prices)), "prices": prices}
