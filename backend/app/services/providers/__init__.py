"""Sources de prix externes.

Chaque provider importe des relevés dans la table `price_observations`
avec son propre `source` et un `external_id` unique. Le reste de l'API
(comparaison, panier, score) ne sait pas d'où vient un prix : ajouter une
source (une enseigne, un autre jeu de données) = écrire un nouveau provider.
"""
from sqlalchemy.orm import Session

from app.models import Product
from app.services.providers.base import PriceProvider
from app.services.providers.open_prices import OpenPricesProvider

PROVIDERS: list[PriceProvider] = [OpenPricesProvider()]


def sync_product_prices(db: Session, product: Product) -> int:
    imported = 0
    for provider in PROVIDERS:
        try:
            imported += provider.sync_product(db, product)
        except Exception as exc:  # une source en panne ne doit jamais casser la comparaison
            db.rollback()
            print(f"[providers] {provider.name} : {exc}")
    return imported
