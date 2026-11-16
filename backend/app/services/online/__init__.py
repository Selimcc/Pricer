"""Prix lus sur les sites des enseignes : phase de test, usage personnel.

Ce module n'est actif qu'avec ENABLE_ONLINE_PRICES=true. Les relevés créés ont
la source « online » : ils sont masqués dès que l'option est coupée et
supprimés par `python -m app.jobs.purge --online`. Ils ne doivent jamais
faire partie d'une version publique (conditions d'utilisation des sites,
droit des producteurs de bases de données).

Fonctionnement :
1. `refresh` : pour chaque enseigne, si le cache est périmé, on cherche la page
   du produit et on lit son prix (en parallèle entre enseignes, une page à la
   fois par site) ; le résultat est gardé dans `online_offers`.
2. `attach` : chaque prix trouvé devient un relevé dans les magasins de
   l'enseigne autour de l'utilisateur (ex. prix carrefour.fr -> Carrefour Market).
"""
import re
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import SessionLocal
from app.models import OnlineCatalogUrl, OnlineOffer, OnlineRetailerState, PriceObservation, Product, Store
from app.services.online import http
from app.services.online.matching import best_urls, scored_urls
from app.services.online.parse import declared_eans, find_offer, page_gtins
from app.services.online.retailers import RETAILERS, Retailer

ERROR_RETRY = timedelta(hours=6)
SAME_PRICE_REFRESH = timedelta(days=3)

_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="online")
_inflight: set[tuple[str, int]] = set()
_inflight_lock = threading.Lock()


def enabled_retailers() -> list[Retailer]:
    keys = [k.strip().lower() for k in settings.online_retailers.split(",") if k.strip()]
    return [RETAILERS[k] for k in keys if k in RETAILERS]


def label_for(user_id: str | None) -> str:
    """« online:carrefour » -> « Prix carrefour.fr »."""
    key = (user_id or "").split(":", 1)[-1]
    return RETAILERS[key].label if key in RETAILERS else "Prix en ligne"


# ---------------------------------------------------------------- état des sites

def is_blocked(db: Session, key: str) -> bool:
    state = db.get(OnlineRetailerState, key)
    return bool(state and state.blocked_until and state.blocked_until > datetime.now(timezone.utc))


def set_status(db: Session, key: str, status: str, block: bool = False) -> None:
    state = db.get(OnlineRetailerState, key) or OnlineRetailerState(retailer=key)
    state.last_status = status[:255]
    state.updated_at = datetime.now(timezone.utc)
    if block:
        state.blocked_until = http.blocked_until()
    db.merge(state)
    db.commit()


def is_fresh(offer: OnlineOffer | None) -> bool:
    if offer is None:
        return False
    age = datetime.now(timezone.utc) - offer.checked_at
    if offer.found:
        return age < timedelta(hours=settings.online_cache_hours)
    if offer.error:
        return age < ERROR_RETRY
    return age < timedelta(days=settings.online_miss_cache_days)


# ---------------------------------------------------------------- recherche d'une page

def candidate_urls(db: Session, client: http.PoliteClient, retailer: Retailer, product: Product,
                   trace: list | None = None) -> tuple[list[str], http.Page | None]:
    """Adresses à essayer, et éventuellement une page déjà téléchargée (recherche -> fiche)."""
    if retailer.direct:
        return [retailer.direct(product.ean)], None
    known = db.scalar(select(OnlineCatalogUrl.url).where(
        OnlineCatalogUrl.retailer == retailer.key, OnlineCatalogUrl.ean == product.ean).limit(1))
    if known:
        return [known], None
    if retailer.search:
        page = client.get(retailer.search(product.ean))
        if retailer.ean_from_url(page.url) == product.ean:  # le site a redirigé vers la fiche
            return [page.url], page
        links = re.findall(retailer.link_re.format(ean=re.escape(product.ean)), page.text) if retailer.link_re else []
        return [httpx.URL(retailer.base_url).join(link).__str__() for link in dict.fromkeys(links)][:2], None
    if retailer.use_sitemaps:
        if trace is not None:
            trace.append({"étape": "candidats sitemap", "scores": scored_urls(db, retailer.key, product)})
        return best_urls(db, retailer.key, product), None
    return [], None


def _save(db: Session, retailer: str, product_id: int, **values) -> None:
    row = {"retailer": retailer, "product_id": product_id, "found": False, "price": None,
           "regular_price": None, "is_promotion": False, "url": None, "error": None,
           "checked_at": datetime.now(timezone.utc), **values}
    stmt = insert(OnlineOffer).values(row)
    db.execute(stmt.on_conflict_do_update(
        constraint="uq_online_offer", set_={k: stmt.excluded[k] for k in row if k not in ("retailer", "product_id")}))
    db.commit()


def _learn_ean(db: Session, retailer: str, url: str, gtins: set[str]) -> None:
    """Une page visitée nous apprend son EAN : la prochaine fois, pas besoin de chercher."""
    ean13 = next((g.zfill(13) for g in gtins if len(g) in (8, 12, 13)), None)
    if ean13:
        db.query(OnlineCatalogUrl).filter(
            OnlineCatalogUrl.retailer == retailer, OnlineCatalogUrl.url == url).update({"ean": ean13})
        db.commit()


def lookup(db: Session, retailer: Retailer, product: Product, client: http.PoliteClient | None = None,
           trace: list | None = None) -> OnlineOffer | None:
    """Cherche le prix d'un produit sur un site et met le cache à jour.

    `trace` (facultatif) reçoit le détail de chaque étape, pour le diagnostic.
    """
    client = client or http.client()
    note = trace.append if trace is not None else (lambda _: None)
    if is_blocked(db, retailer.key):
        note({"étape": "site en pause après un blocage"})
        return None
    if retailer.use_sitemaps and not db.scalar(
            select(OnlineCatalogUrl.id).where(OnlineCatalogUrl.retailer == retailer.key).limit(1)):
        note({"étape": "sitemaps pas encore indexés (lancer : online index)"})
        return None  # ne pas noter le produit comme absent
    try:
        urls, ready = candidate_urls(db, client, retailer, product, trace)
        note({"étape": "pages à essayer", "urls": urls})
        for url in urls:
            page = ready if ready and ready.url == url else client.get(url)
            gtins = page_gtins(page.text) | declared_eans(page.text)
            note({"étape": "page", "url": page.url, "statut": page.status, "eans_page": sorted(gtins)[:5],
                  "page": page})
            if page.status == 404:
                continue
            if gtins and retailer.use_sitemaps:
                _learn_ean(db, retailer.key, url, gtins)
            # Le lecteur propre au site d'abord : il sait où est l'offre principale de la page
            offer = retailer.extract(page.text, product.ean) if retailer.extract else None
            offer = offer or find_offer(page.text, product.ean)
            if offer:
                _save(db, retailer.key, product.id, found=True, price=offer.price, regular_price=offer.regular_price,
                      is_promotion=offer.is_promotion, url=page.url)
                set_status(db, retailer.key, f"ok {page.status}")
                return db.scalar(select(OnlineOffer).where(
                    OnlineOffer.retailer == retailer.key, OnlineOffer.product_id == product.id))
        _save(db, retailer.key, product.id, found=False)
    except http.SiteBlocked as exc:
        db.rollback()
        set_status(db, retailer.key, str(exc), block=True)
        print(f"[online] {retailer.key} bloqué : {exc} (pause {settings.online_block_hours} h)")
    except http.NotAllowed as exc:
        db.rollback()
        _save(db, retailer.key, product.id, found=False, error=str(exc)[:255])
    except (httpx.HTTPError, ValueError) as exc:
        db.rollback()
        _save(db, retailer.key, product.id, found=False, error=f"{type(exc).__name__}: {exc}"[:255])
    return None


def _lookup_job(key: str, product_id: int) -> None:
    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        if product:
            lookup(db, RETAILERS[key], product)
    except Exception as exc:  # une enseigne en panne ne doit jamais casser l'API
        print(f"[online] {key} : {exc}")
    finally:
        db.close()
        with _inflight_lock:
            _inflight.discard((key, product_id))


def refresh(db: Session, product: Product, wait_s: float | None = None) -> None:
    """Lance les recherches périmées et attend au plus `wait_s` secondes ; le reste finit en fond."""
    if not settings.enable_online_prices:
        return
    offers = {o.retailer: o for o in db.scalars(select(OnlineOffer).where(OnlineOffer.product_id == product.id))}
    futures = []
    for retailer in enabled_retailers():
        if is_fresh(offers.get(retailer.key)) or is_blocked(db, retailer.key):
            continue
        job = (retailer.key, product.id)
        with _inflight_lock:
            if job in _inflight:
                continue
            _inflight.add(job)
        futures.append(_pool.submit(_lookup_job, *job))
    if futures:
        wait(futures, timeout=settings.online_wait_s if wait_s is None else wait_s)
    db.expire_all()


# ---------------------------------------------------------------- relevés dans les magasins

def attach(db: Session, products: list[Product], stores: list[tuple[Store, float | None]],
           retailers: dict[str, Retailer] | None = None, require_enabled: bool = True) -> int:
    """Recopie les prix en ligne trouvés vers les magasins de chaque enseigne.

    `retailers` : enseignes concernées (par défaut celles activées) ; l'import du panier
    de la semaine passe toutes les enseignes et `require_enabled=False`.
    """
    if (require_enabled and not settings.enable_online_prices) or not products or not stores:
        return 0
    max_age = datetime.now(timezone.utc) - timedelta(days=7)
    offers = db.scalars(select(OnlineOffer).where(
        OnlineOffer.product_id.in_([p.id for p in products]), OnlineOffer.found.is_(True),
        OnlineOffer.checked_at >= max_age)).all()
    if not offers:
        return 0
    retailers = retailers if retailers is not None else {r.key: r for r in enabled_retailers()}
    store_ids = [s.id for s, _ in stores]
    latest: dict[tuple[int, int, str], PriceObservation] = {}
    for obs in db.scalars(
        select(PriceObservation).where(
            PriceObservation.source == "online",
            PriceObservation.product_id.in_([p.id for p in products]),
            PriceObservation.store_id.in_(store_ids),
        ).order_by(PriceObservation.observed_at)
    ):
        latest[(obs.product_id, obs.store_id, obs.user_id)] = obs

    ean_by_id = {p.id: p.ean for p in products}
    rows = []
    for offer in offers:
        retailer = retailers.get(offer.retailer)
        if not retailer:
            continue
        user_id = f"online:{retailer.key}"
        for store, _ in stores:
            if not retailer.applies_to(store.chain):
                continue
            last = latest.get((offer.product_id, store.id, user_id))
            if last and last.price == offer.price and offer.checked_at - last.observed_at < SAME_PRICE_REFRESH:
                continue
            rows.append({
                "product_id": offer.product_id, "store_id": store.id, "user_id": user_id,
                "price": offer.price, "regular_price": offer.regular_price,
                "is_promotion": offer.is_promotion, "promotion_type": "sale" if offer.is_promotion else None,
                "promotion_label": "Promotion" if offer.is_promotion else None,
                "source": "online", "gps_verified": False, "flagged": False,
                "external_id": f"{retailer.key}:{ean_by_id[offer.product_id]}:{store.id}:{offer.checked_at:%Y%m%d}",
                "observed_at": offer.checked_at,
            })
    if not rows:
        return 0
    result = db.execute(insert(PriceObservation).values(rows)
                        .on_conflict_do_nothing(constraint="uq_observations_source_external")
                        .returning(PriceObservation.id))
    count = len(result.all())
    db.commit()
    return count


def sync(db: Session, product: Product, stores: list[tuple[Store, float | None]]) -> int:
    """Pour l'affichage d'une fiche produit : met à jour les prix en ligne puis les place dans les magasins."""
    if not settings.enable_online_prices:
        return 0
    try:
        refresh(db, product)
        return attach(db, [product], stores)
    except Exception as exc:
        db.rollback()
        print(f"[online] {exc}")
        return 0
