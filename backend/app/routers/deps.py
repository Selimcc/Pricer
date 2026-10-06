import re

from fastapi import HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from app.schemas.schemas import USER_ID_PATTERN
from app.services import openfoodfacts
from app.services.ean import normalize_ean

_USER_RE = re.compile(USER_ID_PATTERN)


def api_error(status: int, code: str, message: str) -> HTTPException:
    """Erreurs avec un `code` stable (pour l'app) et un message lisible (pour l'humain)."""
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def valid_user_id(user_id: str = Path(...)) -> str:
    if not _USER_RE.match(user_id):
        raise api_error(422, "invalid_user", "Identifiant utilisateur invalide.")
    return user_id


def clean_ean(raw: str) -> str:
    ean = normalize_ean(raw)
    if not ean:
        raise api_error(422, "invalid_ean", "Ce code-barres n'est pas valide. La lecture a probablement échoué : rescanne le produit.")
    return ean


def find_product(db: Session, raw_ean: str) -> Product | None:
    return db.scalar(select(Product).where(Product.ean == clean_ean(raw_ean)))


def resolve_product(db: Session, raw_ean: str) -> Product:
    """Produit en base, sinon Open Food Facts (et on le garde), sinon 404."""
    ean = clean_ean(raw_ean)
    product = db.scalar(select(Product).where(Product.ean == ean))
    if product:
        return product
    external = openfoodfacts.lookup_ean(ean)
    if not external:
        raise api_error(404, "product_not_found", "Produit inconnu. Tu peux l'ajouter toi-même.")
    product = Product(ean=ean, **external)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def require_product(db: Session, raw_ean: str) -> Product:
    product = find_product(db, raw_ean)
    if not product:
        raise api_error(404, "product_not_found", "Produit inconnu. Scanne-le d'abord.")
    return product
