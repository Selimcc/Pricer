"""Prix des sites des enseignes : tâches manuelles et tournée de nuit.

    docker compose exec api python -m app.jobs.online status
    docker compose exec api python -m app.jobs.online lookup 3274080005003
    docker compose exec api python -m app.jobs.online index            # sitemaps (Auchan, Monoprix, Franprix)
    docker compose exec api python -m app.jobs.online refresh          # ce que fait le worker chaque nuit
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import settings
from app.db import SessionLocal
from app.models import OnlineOffer, OnlineRetailerState, PriceObservation, Product, ShoppingListItem, Store
from app.routers.deps import resolve_product
from app.services import online
from app.services.online import http
from app.services.online.retailers import RETAILERS
from app.services.online.sitemaps import index_retailer, indexed_count


def cmd_status(db) -> None:
    print(f"ENABLE_ONLINE_PRICES={settings.enable_online_prices}  enseignes={settings.online_retailers}")
    for r in online.enabled_retailers():
        state = db.get(OnlineRetailerState, r.key)
        found = db.scalar(select(func.count()).select_from(OnlineOffer).where(
            OnlineOffer.retailer == r.key, OnlineOffer.found.is_(True))) or 0
        tried = db.scalar(select(func.count()).select_from(OnlineOffer).where(OnlineOffer.retailer == r.key)) or 0
        blocked = state.blocked_until.isoformat(timespec="minutes") if state and state.blocked_until and \
            state.blocked_until > datetime.now(timezone.utc) else "non"
        index = f", index {indexed_count(db, r.key)} pages" if r.use_sitemaps else ""
        print(f"- {r.key:10} trouvés {found}/{tried}{index}, bloqué : {blocked}, "
              f"dernier statut : {state.last_status if state else '-'}")


def _show_trace(trace: list, folder: Path) -> None:
    """Détail des étapes ; chaque page reçue est enregistrée dans data/probe/lookup/ pour l'analyse."""
    for n, step in enumerate(trace):
        page = step.pop("page", None)
        if page is not None:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{n:02d}.html"
            path.write_text(f"<!-- {page.status} {page.url} -->\n{page.text}", encoding="utf-8")
            step["fichier"] = str(path.relative_to(Path(settings.data_dir)))
        if "scores" in step:
            print(f"    {step['étape']} :")
            for score, url in step["scores"]:
                print(f"      {score:4.2f}  {url}")
        else:
            print("    " + " · ".join(f"{k}: {v}" for k, v in step.items()))


def cmd_lookup(db, ean: str) -> None:
    product = resolve_product(db, ean)
    print(f"{product.ean} · marque « {product.brand or ''} » · nom « {product.name} » · {product.quantity or ''}")
    for r in online.enabled_retailers():
        trace: list = []
        offer = online.lookup(db, r, product, trace=trace)
        row = db.scalar(select(OnlineOffer).where(OnlineOffer.retailer == r.key, OnlineOffer.product_id == product.id))
        if offer:
            promo = f" (au lieu de {offer.regular_price} €)" if offer.is_promotion else ""
            print(f"- {r.key:10} {offer.price} €{promo}  {offer.url}")
        elif online.is_blocked(db, r.key):
            print(f"- {r.key:10} site bloqué : {db.get(OnlineRetailerState, r.key).last_status}")
        else:
            print(f"- {r.key:10} pas trouvé{(' : ' + row.error) if row and row.error else ''}")
        _show_trace(trace, Path(settings.data_dir) / "probe" / "lookup" / f"{r.key}-{product.ean}")


def cmd_index(db, keys: list[str]) -> None:
    client = http.client()
    for r in online.enabled_retailers():
        if not r.use_sitemaps or (keys and r.key not in keys):
            continue
        try:
            print(f"- {r.key}: {index_retailer(db, client, r)} pages produit indexées")
        except (http.SiteBlocked, http.NotAllowed) as exc:
            db.rollback()
            online.set_status(db, r.key, f"sitemap : {exc}", block=isinstance(exc, http.SiteBlocked))
            print(f"- {r.key}: impossible ({exc})")
        except Exception as exc:
            db.rollback()
            print(f"- {r.key}: erreur {type(exc).__name__}: {exc}")


def due_products(db, limit: int) -> list[Product]:
    """Produits de listes de courses + produits déjà consultés avec un prix en ligne."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    ids = set(db.scalars(select(ShoppingListItem.product_id).where(ShoppingListItem.checked.is_(False))))
    ids |= set(db.scalars(select(OnlineOffer.product_id).where(
        OnlineOffer.found.is_(True), OnlineOffer.checked_at >= since)))
    return list(db.scalars(select(Product).where(Product.id.in_(ids)).limit(limit))) if ids else []


def cmd_refresh(db, limit: int = 300) -> dict:
    if not settings.enable_online_prices:
        print("[online] ENABLE_ONLINE_PRICES=false : rien à faire")
        return {}
    stats = {"products": 0, "lookups": 0, "attached": 0}
    client = http.client()
    retailers = online.enabled_retailers()
    for product in due_products(db, limit):
        stats["products"] += 1
        offers = {o.retailer: o for o in db.scalars(select(OnlineOffer).where(OnlineOffer.product_id == product.id))}
        for r in retailers:
            if not online.is_fresh(offers.get(r.key)) and not online.is_blocked(db, r.key):
                online.lookup(db, r, product, client)
                stats["lookups"] += 1
        # Magasins qui affichaient déjà un prix en ligne pour ce produit
        store_ids = db.scalars(select(PriceObservation.store_id).where(
            PriceObservation.product_id == product.id, PriceObservation.source == "online").distinct()).all()
        if store_ids:
            stores = [(s, None) for s in db.scalars(select(Store).where(Store.id.in_(store_ids)))]
            stats["attached"] += online.attach(db, [product], stores)
    print(f"[online] {stats['products']} produits, {stats['lookups']} recherches, {stats['attached']} nouveaux relevés")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Prix des sites des enseignes (test personnel).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p_lookup = sub.add_parser("lookup")
    p_lookup.add_argument("ean")
    p_index = sub.add_parser("index")
    p_index.add_argument("retailers", nargs="*", help=f"parmi {', '.join(RETAILERS)} (défaut : toutes)")
    p_refresh = sub.add_parser("refresh")
    p_refresh.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.cmd == "status":
            cmd_status(db)
        elif args.cmd == "lookup":
            cmd_lookup(db, args.ean)
        elif args.cmd == "index":
            cmd_index(db, args.retailers)
        elif args.cmd == "refresh":
            cmd_refresh(db, args.limit)
    finally:
        db.close()


if __name__ == "__main__":
    main()
