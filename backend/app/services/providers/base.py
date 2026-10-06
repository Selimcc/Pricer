from typing import Protocol

from sqlalchemy.orm import Session

from app.models import Product


class PriceProvider(Protocol):
    name: str

    def sync_product(self, db: Session, product: Product) -> int:
        """Importe les prix connus de ce produit. Retourne le nombre de nouveaux relevés."""
        ...
