"""Retrouver la page d'un produit dans un sitemap à partir de son nom.

Les adresses de pages produit reprennent presque toujours marque, nom et
contenance (« cristaline-eau-de-source-1-5l »). On compare ces mots à ceux
de la fiche produit ; la page retenue est ensuite vérifiée par son EAN,
donc une ressemblance trompeuse ne peut pas produire un faux prix.
"""
import re
import unicodedata
from decimal import Decimal
from urllib.parse import unquote, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OnlineCatalogUrl, Product

STOPWORDS = {
    "les", "des", "une", "aux", "avec", "pour", "sans", "sur", "par", "the", "and", "products", "produit",
    "produits", "www", "html", "fr",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", unquote(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def words(text: str) -> list[str]:
    return [w for w in normalize(text).split() if len(w) >= 3 and w not in STOPWORDS and not w.isdigit()]


def slug_of(url: str) -> str:
    # Les identifiants techniques (MPX_3908291, pr-C1234567…) n'aident pas à la recherche
    path = re.sub(r"(?i)(mpx_|pr-c?|c)?\d{5,}", " ", urlsplit(url).path)
    return " ".join(normalize(path).split())


def quantity_variants(product: Product) -> list[str]:
    """Façons d'écrire la contenance dans une adresse : 1-5l, 150cl, 1500ml, 400g…"""
    if product.quantity_value is None or not product.quantity_unit:
        return []
    v = Decimal(product.quantity_value)

    def fmt(x: Decimal) -> str:
        return format(x.normalize(), "f").replace(".", " ")

    if product.quantity_unit == "ml":
        out = [f"{fmt(v)}ml", f"{fmt(v / 10)}cl", f"{fmt(v / 1000)}l", f"{fmt(v / 1000)} l"]
    elif product.quantity_unit == "g":
        out = [f"{fmt(v)}g", f"{fmt(v)} g", f"{fmt(v / 1000)}kg", f"{fmt(v / 1000)} kg"]
    else:
        out = [f"x{fmt(v)}", f"{fmt(v)}x"]
    return [o for o in out if not o.startswith("0 ")]


def score(product_words: set[str], brand_words: set[str], qty: list[str], slug: str) -> float:
    if not product_words:
        return 0.0
    slug_words = set(slug.split())
    if brand_words and not (brand_words & slug_words):
        return 0.0
    overlap = len(product_words & slug_words) / len(product_words)
    padded = f" {slug} "
    bonus = 0.25 if any(f" {q} " in padded for q in qty) else 0.0
    return overlap + bonus


def scored_urls(db: Session, retailer: str, product: Product, limit: int = 5) -> list[tuple[float, str]]:
    """Meilleures pages candidates avec leur score (pour le diagnostic)."""
    brand = set(words(product.brand or "")[:2])
    name = set(words(product.name or ""))
    all_words = brand | name
    if not all_words:
        return []
    # Le mot le plus rare (en pratique la marque, sinon le plus long) filtre en base
    key = sorted(brand)[0] if brand else max(name, key=len)
    rows = db.execute(
        select(OnlineCatalogUrl.url, OnlineCatalogUrl.slug)
        .where(OnlineCatalogUrl.retailer == retailer, OnlineCatalogUrl.slug.like(f"%{key}%"))
        .limit(3000)
    ).all()
    qty = quantity_variants(product)
    return sorted(((round(score(all_words, brand, qty, slug), 2), url) for url, slug in rows), reverse=True)[:limit]


def best_urls(db: Session, retailer: str, product: Product, limit: int = 4, threshold: float = 0.5) -> list[str]:
    """Pages à visiter. Le seuil est bas exprès : chaque page est vérifiée par son EAN avant
    d'accepter un prix, et chaque visite apprend l'EAN de la page pour les recherches suivantes
    (les fiches Open Food Facts ont parfois un nom pauvre, ex. « isabelle » pour une Cristaline)."""
    return [url for s, url in scored_urls(db, retailer, product, limit) if s >= threshold]
