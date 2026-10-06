"""Open Prices (Open Food Facts) : base ouverte de prix réels, avec preuves.

Chaque prix y est rattaché à un magasin OpenStreetMap, comme nos magasins :
les deux se rejoignent naturellement par (osm_type, osm_id).
Données sous licence ODbL : l'application doit citer la source.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PriceObservation, Product
from app.services.osm import get_or_create_osm_store

PROOF_BASE_URL = "https://prices.openfoodfacts.org/img/"

DISCOUNT_TYPES = {
    "QUANTITY": "multi_buy",
    "SALE": "sale",
    "SEASONAL": "sale",
    "LOYALTY_PROGRAM": "loyalty",
    "EXPIRES_SOON": "clearance",
}

PROMOTION_LABELS = {
    "sale": "Promotion",
    "loyalty": "Prix fidélité",
    "multi_buy": "Offre quantité",
    "bundle": "Lot",
    "clearance": "Date courte",
    "coupon": "Bon de réduction",
    "other": "Offre",
}


def _parse_date(value: str | None) -> datetime | None:
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return datetime.combine(d, time(12, 0), tzinfo=timezone.utc)


def parse_price_item(item: dict) -> tuple[dict, dict] | None:
    """Item Open Prices -> (magasin OSM, relevé) ou None s'il est inutilisable."""
    if item.get("type") not in (None, "PRODUCT") or item.get("price_per"):
        return None
    if (item.get("currency") or "EUR") != "EUR" or item.get("duplicate_of"):
        return None
    loc = item.get("location") or {}
    if loc.get("type") not in (None, "OSM") or not loc.get("osm_id"):
        return None
    if loc.get("osm_lat") is None or loc.get("osm_lon") is None or item.get("price") is None:
        return None
    observed_at = _parse_date(item.get("date"))
    if observed_at is None:
        return None

    name = loc.get("osm_name") or loc.get("osm_brand") or "Magasin"
    store = {
        "osm_type": str(loc.get("osm_type") or "node").lower(),
        "osm_id": int(loc["osm_id"]),
        "name": name[:255],
        "chain": (loc.get("osm_brand") or name)[:100],
        "address": None,
        "city": loc.get("osm_address_city"),
        "postcode": loc.get("osm_address_postcode"),
        "latitude": float(loc["osm_lat"]),
        "longitude": float(loc["osm_lon"]),
        "shop_type": loc.get("osm_tag_value"),
        "source": "open_prices",
    }

    discounted = bool(item.get("price_is_discounted"))
    promo_type = DISCOUNT_TYPES.get(item.get("discount_type") or "", "sale" if discounted else None)
    if not discounted:
        promo_type = None
    proof = item.get("proof") or {}
    observation = {
        "price": Decimal(str(item["price"])).quantize(Decimal("0.01")),
        "is_promotion": discounted,
        "promotion_type": promo_type,
        "promotion_label": PROMOTION_LABELS.get(promo_type) if promo_type else None,
        "regular_price": (
            Decimal(str(item["price_without_discount"])).quantize(Decimal("0.01"))
            if item.get("price_without_discount") else None
        ),
        "proof_image_url": PROOF_BASE_URL + proof["file_path"] if proof.get("file_path") else None,
        "user_id": f"open_prices:{item.get('owner') or 'anonymous'}"[:100],
        "source": "open_prices",
        "external_id": str(item["id"]),
        "observed_at": observed_at,
        "gps_verified": False,
        "flagged": False,
    }
    return store, observation


class OpenPricesProvider:
    name = "open_prices"

    def fetch(self, ean: str) -> list[dict]:
        response = httpx.get(
            f"{settings.open_prices_url}/prices",
            params={"product_code": ean, "size": 100, "order_by": "-date"},
            headers={"User-Agent": settings.http_user_agent},
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json().get("items", [])

    def sync_product(self, db: Session, product: Product) -> int:
        if not settings.enable_open_prices:
            return 0
        now = datetime.now(timezone.utc)
        if product.prices_synced_at and now - product.prices_synced_at < timedelta(hours=settings.open_prices_sync_hours):
            return 0

        items = self.fetch(product.ean)
        stores_cache: dict[tuple[str, int], int] = {}
        rows = []
        for item in items:
            parsed = parse_price_item(item)
            if not parsed:
                continue
            store_data, obs = parsed
            key = (store_data["osm_type"], store_data["osm_id"])
            if key not in stores_cache:
                stores_cache[key] = get_or_create_osm_store(db, store_data).id
            rows.append({**obs, "product_id": product.id, "store_id": stores_cache[key]})

        inserted = 0
        if rows:
            result = db.execute(
                insert(PriceObservation).values(rows)
                .on_conflict_do_nothing(constraint="uq_observations_source_external")
                .returning(PriceObservation.id)
            )
            inserted = len(result.all())
        product.prices_synced_at = now
        db.commit()
        return inserted
