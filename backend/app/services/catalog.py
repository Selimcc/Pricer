"""Catalogue produits : à qui demander « c'est quoi ce code-barres ? ».

Ordre de recherche :
1. notre base (tout produit déjà vu ou créé par un utilisateur) ;
2. les bases ouvertes de la famille Open Food Facts, interrogées en parallèle,
   ce qui couvre tout le supermarché, pas seulement l'alimentaire.

Plus notre base grossit (scans, créations, photos), moins on dépend des
sources externes : elles ne servent qu'au premier scan d'un produit.
"""
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.core.config import settings
from app.services import quantity as qty

# (code source, domaine) par ordre de priorité si plusieurs bases connaissent le produit
SOURCES = [
    ("off", "world.openfoodfacts.org"),       # alimentation, boissons
    ("obf", "world.openbeautyfacts.org"),     # hygiène, beauté
    ("opff", "world.openpetfoodfacts.org"),   # animaux
    ("opf", "world.openproductsfacts.org"),   # entretien, maison, tout le reste
]

FAMILIES = {
    "off": "Alimentation",
    "obf": "Hygiène et beauté",
    "opff": "Animaux",
    "opf": "Maison et entretien",
    "user": "Ajouté par la communauté",
    "demo": "Alimentation",
}

FIELDS = (
    "product_name,product_name_fr,generic_name_fr,brands,quantity,product_quantity,"
    "product_quantity_unit,image_front_url,image_url,nutriscore_grade"
)


def fetch_from(source: str, domain: str, ean: str) -> dict | None:
    try:
        response = httpx.get(
            f"https://{domain}/api/v2/product/{ean}.json",
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
    if data.get("status") != 1 or not data.get("product"):
        return None
    return parse_product(data["product"], source)


def lookup_ean(ean: str) -> dict | None:
    """Cherche le produit dans toutes les bases ouvertes en même temps."""
    if not settings.enable_openfoodfacts:
        return None
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        futures = [pool.submit(fetch_from, source, domain, ean) for source, domain in SOURCES]
        results = [f.result() for f in futures]
    found = [r for r in results if r]
    if not found:
        return None
    # Priorité à la fiche la plus complète, puis à l'ordre des sources
    found.sort(key=lambda r: (r["name"] == UNNAMED, r["image_url"] is None))
    return found[0]


UNNAMED = "Produit sans nom"


def parse_product(p: dict, source: str = "off") -> dict:
    value, unit = qty.from_off(p.get("product_quantity"), p.get("product_quantity_unit"), p.get("quantity"))
    brands = (p.get("brands") or "").split(",")
    grade = (p.get("nutriscore_grade") or "").lower()
    name = p.get("product_name_fr") or p.get("product_name") or p.get("generic_name_fr") or UNNAMED
    return {
        "name": name.strip()[:255] or UNNAMED,
        "brand": brands[0].strip()[:255] if brands and brands[0].strip() else None,
        "quantity": (p.get("quantity") or None),
        "image_url": p.get("image_front_url") or p.get("image_url"),
        "quantity_value": value,
        "quantity_unit": unit,
        "nutriscore_grade": grade if source == "off" and grade in ("a", "b", "c", "d", "e") else None,
        "source": source,
    }
