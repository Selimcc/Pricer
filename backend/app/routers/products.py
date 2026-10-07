from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models import PriceObservation, Product, Store
from app.routers.deps import api_error, clean_ean, require_product, resolve_product
from app.schemas import ProductCreate, ProductOut
from app.schemas.schemas import USER_ID_PATTERN
from app.services import geo, online, osm, pricing
from app.services.providers import sync_product_prices
from app.services.quantity import parse_quantity
from app.services.storage import ALLOWED_TYPES, storage

router = APIRouter(prefix="/products", tags=["Produits"])

FALLBACK_RADIUS_KM = 50
FALLBACK_MAX_AGE_DAYS = 365


@router.get("/search", response_model=list[ProductOut])
def search_products(q: str = Query(..., min_length=2, max_length=80), limit: int = Query(15, ge=1, le=50),
                    db: Session = Depends(get_db)):
    """Recherche texte dans les produits déjà connus (scannés par quelqu'un)."""
    pattern = f"%{q.strip()}%"
    return db.scalars(
        select(Product)
        .where(or_(Product.name.ilike(pattern), Product.brand.ilike(pattern), Product.ean.like(f"{q.strip()}%")))
        .order_by(Product.name)
        .limit(limit)
    ).all()


@router.post("", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    ean = clean_ean(payload.ean)
    if db.scalar(select(Product).where(Product.ean == ean)):
        raise api_error(409, "product_exists", "Ce produit existe déjà.")
    value, unit = parse_quantity(payload.quantity)
    product = Product(
        ean=ean, name=payload.name.strip(), brand=(payload.brand or "").strip() or None,
        quantity=payload.quantity, quantity_value=value, quantity_unit=unit, source="user",
        created_by=payload.user_id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{ean}", response_model=ProductOut)
def get_product(ean: str, db: Session = Depends(get_db)):
    return resolve_product(db, ean)


@router.post("/{ean}/image", response_model=ProductOut)
async def add_product_image(ean: str, file: UploadFile = File(...), user_id: str = Form(..., pattern=USER_ID_PATTERN),
                            db: Session = Depends(get_db)):
    """Photo de l'emballage pour un produit qui n'en a pas (catalogue maison).

    Une photo existante n'est jamais remplacée : ça évite qu'un seul
    utilisateur puisse dégrader une fiche correcte.
    """
    product = require_product(db, ean)
    if product.image_url:
        raise api_error(409, "image_exists", "Ce produit a déjà une photo.")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
        raise api_error(415, "bad_image", "Format d'image non pris en charge (JPEG, PNG ou WebP).")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise api_error(413, "image_too_large", f"Photo trop lourde (max {settings.max_upload_mb} Mo).")
    product.image_url = storage.save(data, content_type)
    product.image_added_by = user_id
    db.commit()
    db.refresh(product)
    return product


@router.get("/{ean}/comparison")
def comparison(
    ean: str,
    latitude: float = Query(48.8566, ge=-90, le=90),
    longitude: float = Query(2.3522, ge=-180, le=180),
    radius_km: float = Query(10, gt=0, le=50),
    user_id: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    """Prix actuels du produit dans les magasins autour du point, du moins cher au plus cher."""
    product = require_product(db, ean)

    import_status = osm.ensure_area_imported(db, latitude, longitude, radius_km)
    sync_product_prices(db, product)

    stores = geo.stores_within(db, latitude, longitude, radius_km)
    online.sync(db, product, stores)
    rows = list(pricing.current_prices(db, [product], stores, user_id).values())
    rows.sort(key=lambda r: (r["price"], -r["confidence"]))

    best_price = rows[0]["price"] if rows else None
    for index, row in enumerate(rows):
        row["rank"] = index + 1
        row["savings_vs_best"] = round(row["price"] - best_price, 2)

    stats = pricing.price_stats(db, product)

    # Rien de proche et récent : on montre quand même ce qu'on sait, à titre indicatif,
    # plutôt que de répondre « aucun prix » alors que des relevés existent.
    fallback = None
    if not rows:
        far_stores = geo.stores_within(db, latitude, longitude, FALLBACK_RADIUS_KM, limit=1000)
        far_rows = pricing.current_prices(db, [product], far_stores, user_id, max_age_days=FALLBACK_MAX_AGE_DAYS)
        nearest_rows = sorted(far_rows.values(), key=lambda r: r["distance_km"])[:5]
        fallback = {
            "radius_km": FALLBACK_RADIUS_KM,
            "max_age_days": FALLBACK_MAX_AGE_DAYS,
            "results": nearest_rows,
            "price_stats": pricing.price_stats(db, product, days=FALLBACK_MAX_AGE_DAYS),
        }

    nearest = min(rows, key=lambda r: r["distance_km"]) if rows else None
    sources: dict[str, int] = {}
    for r in rows:
        sources[r["source"]] = sources.get(r["source"], 0) + 1

    return {
        "product": ProductOut.model_validate(product),
        "results": rows,
        "best_price": best_price,
        "store_count": len(rows),
        "potential_savings": round(rows[-1]["price"] - rows[0]["price"], 2) if len(rows) > 1 else 0,
        "nearest_store_id": nearest["store_id"] if nearest else None,
        "price_stats": stats,
        "deal": pricing.deal_for(best_price, stats),
        "sources": sources,
        "fallback": fallback,
        "area": {
            "radius_km": radius_km,
            "stores_in_area": len(stores),
            "osm_import": "failed" if import_status is None else ("imported" if import_status else "cached"),
        },
    }


@router.get("/{ean}/history")
def history(ean: str, days: int = Query(90, ge=7, le=365), db: Session = Depends(get_db)):
    """Tous les relevés récents du produit (pour un graphique d'évolution)."""
    product = require_product(db, ean)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(PriceObservation, Store)
        .join(Store, Store.id == PriceObservation.store_id)
        .where(PriceObservation.product_id == product.id, PriceObservation.observed_at >= since, pricing.visible())
        .order_by(PriceObservation.observed_at)
    ).all()
    return {
        "product": ProductOut.model_validate(product),
        "stats": pricing.price_stats(db, product, days),
        "points": [
            {
                "observed_at": obs.observed_at,
                "price": float(obs.price),
                "is_promotion": obs.is_promotion,
                "chain": store.chain,
                "store_name": store.name,
                "source": obs.source,
            }
            for obs, store in rows
        ],
    }
