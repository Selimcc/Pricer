"""Complète les fiches créées par l'import Open Prices (nom seul, parfois « Produit 356… »).

Les plus utiles d'abord (produits avec le plus de prix). Rythme lent pour
respecter les limites d'Open Food Facts : une fiche par seconde environ.

    docker compose exec api python -m app.jobs.enrich --limit 200
"""
import argparse
import time

from sqlalchemy import func, select

from app.core.config import settings
from app.db import SessionLocal
from app.jobs.open_prices_import import STUB_SOURCE
from app.models import PriceObservation, Product
from app.routers.deps import complete_imported


def run(limit: int = 300, delay_s: float = 1.0) -> dict:
    if not settings.enable_openfoodfacts:
        return {"done": 0}
    db = SessionLocal()
    stats = {"done": 0, "named": 0}
    try:
        counts = (select(PriceObservation.product_id, func.count().label("n"))
                  .group_by(PriceObservation.product_id).subquery())
        products = db.scalars(
            select(Product).join(counts, counts.c.product_id == Product.id)
            .where(Product.source == STUB_SOURCE).order_by(counts.c.n.desc()).limit(limit)
        ).all()
        for product in products:
            complete_imported(db, product)
            stats["done"] += 1
            stats["named"] += product.source != "open_prices"
            time.sleep(delay_s)
    finally:
        db.close()
    print(f"[enrich] {stats['done']} fiches traitées, {stats['named']} complétées depuis Open Food Facts", flush=True)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Complète les fiches produits importées d'Open Prices.")
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()
    run(args.limit)


if __name__ == "__main__":
    main()
