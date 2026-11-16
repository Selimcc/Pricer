"""Cœur métier : « quel est le prix actuel de ce produit dans ce magasin ? »

Règles :
- on garde un seul prix par (produit, magasin) : le relevé le plus récent
  encore vivant (pas massivement contesté) de moins de N jours ;
- chaque prix est accompagné de son score de confiance et de son prix au kilo/litre.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ObservationVote, PriceObservation, Product, Store
from app.services.quantity import unit_price
from app.services.scoring import confidence_for

SOURCE_LABELS = {"community": "Communauté", "receipt": "Ticket de caisse", "open_prices": "Open Prices",
                 "online": "Prix en ligne", "demo": "Démo"}


def visible():
    """Filtre des relevés montrables : les prix d'origine « online » ne sont jamais affichés."""
    return PriceObservation.source != "online"


def source_label(obs: PriceObservation) -> str:
    return SOURCE_LABELS.get(obs.source, obs.source)


def public_proof_url(url: str | None) -> str | None:
    """Les tickets de caisse servent de preuve mais ne sont jamais montrés (données personnelles)."""
    if url and (url.startswith("http") or url.startswith("/uploads/")):
        return url
    return None


def vote_counts(db: Session, observation_ids: list[int]) -> dict[int, tuple[int, int]]:
    if not observation_ids:
        return {}
    rows = db.execute(
        select(
            ObservationVote.observation_id,
            func.sum(case((ObservationVote.vote == 1, 1), else_=0)),
            func.sum(case((ObservationVote.vote == -1, 1), else_=0)),
        )
        .where(ObservationVote.observation_id.in_(observation_ids))
        .group_by(ObservationVote.observation_id)
    ).all()
    return {oid: (int(c or 0), int(r or 0)) for oid, c, r in rows}


def is_disputed(confirmations: int, rejections: int) -> bool:
    """Relevé que la communauté considère comme faux / plus valable."""
    return rejections >= 2 and rejections >= confirmations + 2


def observation_row(obs: PriceObservation, store: Store, product: Product, distance_km: float | None,
                    votes: tuple[int, int], user_id: str | None = None, user_vote: int | None = None) -> dict:
    confirmations, rejections = votes
    conf = confidence_for(
        obs.observed_at, confirmations, rejections,
        has_proof=bool(obs.proof_image_url), gps_verified=obs.gps_verified, flagged=obs.flagged,
    )
    price = float(obs.price)
    per_unit, per_unit_label = unit_price(price, product.quantity_value, product.quantity_unit)
    return {
        "observation_id": obs.id,
        "store_id": store.id,
        "store_name": store.name,
        "chain": store.chain,
        "store_city": store.city,
        "store_latitude": store.latitude,
        "store_longitude": store.longitude,
        "price": price,
        "regular_price": float(obs.regular_price) if obs.regular_price is not None else None,
        "unit_price": per_unit,
        "unit_price_label": per_unit_label,
        "is_promotion": obs.is_promotion,
        "promotion_type": obs.promotion_type,
        "promotion_label": obs.promotion_label,
        "observed_at": obs.observed_at,
        "distance_km": distance_km,
        "confirmations": confirmations,
        "rejections": rejections,
        "confirmation_score": round((conf["community"] / 100 * 2 - 1) * 100, 1),
        "has_proof": bool(obs.proof_image_url),
        "proof_image_url": public_proof_url(obs.proof_image_url),
        "gps_verified": obs.gps_verified,
        "source": obs.source,
        "source_label": source_label(obs),
        "is_mine": bool(user_id) and obs.user_id == user_id,
        "my_vote": user_vote,
        **conf,
    }


def current_prices(
    db: Session,
    products: list[Product],
    stores: list[tuple[Store, float]],
    user_id: str | None = None,
    max_age_days: int | None = None,
) -> dict[tuple[int, int], dict]:
    """Prix actuel pour chaque couple (produit, magasin) -> ligne enrichie."""
    if not products or not stores:
        return {}
    product_by_id = {p.id: p for p in products}
    store_by_id = {s.id: (s, d) for s, d in stores}
    since = datetime.now(timezone.utc) - timedelta(days=max_age_days or settings.price_max_age_days)

    observations = db.scalars(
        select(PriceObservation)
        .where(
            PriceObservation.product_id.in_(product_by_id),
            PriceObservation.store_id.in_(store_by_id),
            PriceObservation.observed_at >= since,
            visible(),
        )
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    ).all()
    votes = vote_counts(db, [o.id for o in observations])
    my_votes = {}
    if user_id and observations:
        my_votes = dict(db.execute(
            select(ObservationVote.observation_id, ObservationVote.vote).where(
                ObservationVote.user_id == user_id,
                ObservationVote.observation_id.in_([o.id for o in observations]),
            )
        ).all())

    result: dict[tuple[int, int], dict] = {}
    for obs in observations:
        key = (obs.product_id, obs.store_id)
        if key in result:
            continue
        v = votes.get(obs.id, (0, 0))
        if is_disputed(*v):
            continue
        store, distance = store_by_id[obs.store_id]
        result[key] = observation_row(obs, store, product_by_id[obs.product_id], distance, v, user_id, my_votes.get(obs.id))
    return result


def price_stats(db: Session, product: Product, days: int = 90) -> dict | None:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    prices = [float(p) for p in db.scalars(
        select(PriceObservation.price).where(
            PriceObservation.product_id == product.id,
            PriceObservation.observed_at >= since,
            PriceObservation.flagged.is_(False),
            visible(),
        )
    ).all()]
    if not prices:
        return None
    return {
        "min": round(min(prices), 2),
        "median": round(median(prices), 2),
        "max": round(max(prices), 2),
        "count": len(prices),
        "days": days,
    }


def deal_for(best_price: float | None, stats: dict | None) -> dict | None:
    """« Bon plan » : prix nettement sous le prix habituel constaté."""
    if best_price is None or not stats or stats["count"] < 4 or stats["median"] <= 0:
        return None
    gap = (stats["median"] - best_price) / stats["median"]
    if gap < 0.08:
        return None
    return {"percent": round(gap * 100), "label": f"{round(gap * 100)} % sous le prix habituel"}


def recent_median(db: Session, product_id: int, days: int = 90) -> tuple[float | None, int]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    prices = [float(p) for p in db.scalars(
        select(PriceObservation.price).where(
            PriceObservation.product_id == product_id,
            PriceObservation.observed_at >= since,
            PriceObservation.flagged.is_(False),
            visible(),
        )
    ).all()]
    return (median(prices) if prices else None), len(prices)


def group_by_store(rows: dict[tuple[int, int], dict]) -> dict[int, dict[int, dict]]:
    by_store: dict[int, dict[int, dict]] = defaultdict(dict)
    for (product_id, store_id), row in rows.items():
        by_store[store_id][product_id] = row
    return by_store
