"""Ménage avant de montrer l'app à d'autres personnes (ou avant une release).

    docker compose exec api python -m app.jobs.purge --online   # prix lus sur les sites des enseignes
    docker compose exec api python -m app.jobs.purge --demo     # magasins et prix fictifs (mettre SEED_DEMO=false)
"""
import argparse

from sqlalchemy import delete, exists, select

from app.core.config import settings
from app.db import SessionLocal
from app.models import (
    ObservationVote,
    OnlineCatalogUrl,
    OnlineOffer,
    OnlineRetailerState,
    PriceObservation,
    Receipt,
    Store,
)


def _delete_observations(db, source: str) -> int:
    ids = select(PriceObservation.id).where(PriceObservation.source == source)
    db.execute(delete(ObservationVote).where(ObservationVote.observation_id.in_(ids)))
    return db.execute(delete(PriceObservation).where(PriceObservation.source == source)).rowcount or 0


def purge_online(db, keep_index: bool = False) -> int:
    count = _delete_observations(db, "online")
    db.execute(delete(OnlineOffer))
    db.execute(delete(OnlineRetailerState))
    if not keep_index:
        db.execute(delete(OnlineCatalogUrl))
    db.commit()
    return count


def purge_demo(db) -> tuple[int, int]:
    count = _delete_observations(db, "demo")
    used = exists().where(PriceObservation.store_id == Store.id)
    used_receipt = exists().where(Receipt.store_id == Store.id)
    stores = db.execute(delete(Store).where(Store.source == "demo", ~used, ~used_receipt)).rowcount or 0
    db.commit()
    return count, stores


def main() -> None:
    parser = argparse.ArgumentParser(description="Supprime des données qui ne doivent pas être publiées.")
    parser.add_argument("--online", action="store_true", help="prix lus sur les sites des enseignes")
    parser.add_argument("--keep-index", action="store_true", help="garder l'index des sitemaps")
    parser.add_argument("--demo", action="store_true", help="magasins et prix de démonstration")
    args = parser.parse_args()
    if not (args.online or args.demo):
        parser.error("préciser --online et/ou --demo")
    db = SessionLocal()
    try:
        if args.online:
            print(f"[purge] {purge_online(db, args.keep_index)} prix en ligne supprimés")
        if args.demo:
            prices, stores = purge_demo(db)
            print(f"[purge] {prices} prix de démo et {stores} magasins de démo supprimés")
            if settings.seed_demo:
                print("[purge] Attention : SEED_DEMO=true, la démo sera recréée au prochain démarrage.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
