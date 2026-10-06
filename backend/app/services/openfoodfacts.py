"""Résolution d'un EAN via Open Food Facts (nom, marque, photo, quantité)."""
import httpx

from app.core.config import settings
from app.services import quantity as qty

FIELDS = "product_name,product_name_fr,brands,quantity,product_quantity,product_quantity_unit,image_front_url,image_url,nutriscore_grade"


def lookup_ean(ean: str) -> dict | None:
    if not settings.enable_openfoodfacts:
        return None
    url = f"https://world.openfoodfacts.org/api/v2/product/{ean}.json"
    try:
        response = httpx.get(
            url,
            params={"fields": FIELDS},
            headers={"User-Agent": settings.http_user_agent},
            timeout=6.0,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None
    if data.get("status") != 1:
        return None
    return parse_off_product(data.get("product") or {})


def parse_off_product(p: dict) -> dict:
    value, unit = qty.from_off(p.get("product_quantity"), p.get("product_quantity_unit"), p.get("quantity"))
    brands = (p.get("brands") or "").split(",")
    grade = (p.get("nutriscore_grade") or "").lower()
    return {
        "name": (p.get("product_name_fr") or p.get("product_name") or "Produit sans nom").strip()[:255],
        "brand": brands[0].strip()[:255] if brands and brands[0].strip() else None,
        "quantity": (p.get("quantity") or None),
        "image_url": p.get("image_front_url") or p.get("image_url"),
        "quantity_value": value,
        "quantity_unit": unit,
        "nutriscore_grade": grade if grade in ("a", "b", "c", "d", "e") else None,
        "source": "off",
    }
