from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models import ObservationVote, PriceObservation, Product, Store
from app.routers.deps import api_error, require_product
from app.schemas import ObservationCreate, VoteCreate
from app.services import pricing, ratelimit
from app.services.providers.open_prices import PROMOTION_LABELS
from app.services.scoring import confidence_for, haversine_km
from app.services.storage import ALLOWED_TYPES, storage

router = APIRouter(prefix="/observations", tags=["Relevés de prix"])

DUPLICATE_WINDOW = timedelta(hours=6)


@router.get("/recent")
def recent_observations(limit: int = Query(12, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.execute(
        select(PriceObservation, Product, Store)
        .join(Product, Product.id == PriceObservation.product_id)
        .join(Store, Store.id == PriceObservation.store_id)
        # Le fil « derniers relevés » montre l'activité des gens, pas les imports automatiques
        .where(PriceObservation.source.not_in(("online",)))
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
        .limit(limit)
    ).all()
    votes = pricing.vote_counts(db, [obs.id for obs, _, _ in rows])
    result = []
    for obs, product, store in rows:
        c, r = votes.get(obs.id, (0, 0))
        conf = confidence_for(obs.observed_at, c, r, has_proof=bool(obs.proof_image_url),
                              gps_verified=obs.gps_verified, flagged=obs.flagged)
        result.append({
            "id": obs.id,
            "ean": product.ean,
            "product": product.name,
            "brand": product.brand,
            "image_url": product.image_url,
            "store": store.name,
            "chain": store.chain,
            "city": store.city,
            "price": float(obs.price),
            "promotion": obs.promotion_label if obs.is_promotion else None,
            "observed_at": obs.observed_at,
            "source": obs.source,
            "gps_verified": obs.gps_verified,
            "has_proof": bool(obs.proof_image_url),
            "flagged": obs.flagged,
            "confirmations": c,
            "rejections": r,
            **conf,
        })
    return result


@router.post("")
def create_observation(payload: ObservationCreate, db: Session = Depends(get_db)):
    product = require_product(db, payload.ean)
    store = db.get(Store, payload.store_id)
    if not store:
        raise api_error(404, "store_not_found", "Magasin introuvable.")

    if not ratelimit.allow(f"obs:{payload.user_id}", settings.max_contributions_per_hour):
        raise api_error(429, "rate_limited", "Beaucoup de relevés en peu de temps. Réessaie un peu plus tard.")

    # Présence en magasin : on refuse seulement si c'est clairement impossible,
    # sinon le relevé est accepté et le GPS vérifié augmente sa confiance.
    distance_m, gps_verified = None, False
    if payload.latitude is not None and payload.longitude is not None:
        distance_km = haversine_km(payload.latitude, payload.longitude, store.latitude, store.longitude)
        distance_m = round(distance_km * 1000)
        if distance_km > settings.gps_max_distance_km:
            raise api_error(
                400, "too_far",
                f"Tu es à {distance_km:.1f} km de ce magasin. Un relevé doit être fait sur place.",
            )
        gps_verified = distance_m <= settings.gps_verified_radius_m

    # Prix anormal par rapport à ce qu'on connaît : accepté mais signalé.
    flagged = False
    med, count = pricing.recent_median(db, product.id)
    if med and count >= 3 and not (0.4 * med <= float(payload.price) <= 2.5 * med):
        flagged = True

    promo_type = payload.promotion_type if payload.is_promotion else None
    if payload.is_promotion and not promo_type:
        promo_type = "sale"
    label = (payload.promotion_label or PROMOTION_LABELS.get(promo_type or "", "")) if payload.is_promotion else None

    values = dict(
        price=payload.price, is_promotion=payload.is_promotion, promotion_type=promo_type,
        promotion_label=label or None,
        regular_price=payload.regular_price if payload.is_promotion else None,
        latitude=payload.latitude, longitude=payload.longitude,
        gps_distance_m=distance_m, gps_verified=gps_verified, flagged=flagged,
        observed_at=datetime.now(timezone.utc),
    )

    # Même personne, même produit, même magasin, il y a peu : on corrige au lieu de dupliquer.
    recent = db.scalar(
        select(PriceObservation).where(
            PriceObservation.user_id == payload.user_id,
            PriceObservation.product_id == product.id,
            PriceObservation.store_id == store.id,
            PriceObservation.source == "community",
            PriceObservation.observed_at >= datetime.now(timezone.utc) - DUPLICATE_WINDOW,
        ).order_by(PriceObservation.observed_at.desc())
    )
    if recent:
        for k, v in values.items():
            setattr(recent, k, v)
        obs, status = recent, "updated"
    else:
        obs = PriceObservation(product_id=product.id, store_id=store.id, user_id=payload.user_id,
                               source="community", proof_image_url=payload.proof_image_url, **values)
        db.add(obs)
        status = "created"
    db.commit()
    db.refresh(obs)

    message = "Merci ! Ton prix est en ligne."
    if flagged:
        message = "Prix enregistré, mais il est très différent des autres relevés : il sera vérifié par la communauté."
    elif not gps_verified:
        message = "Prix enregistré. Ajoute une photo de l'étiquette pour qu'il soit plus fiable."
    return {"id": obs.id, "status": status, "gps_verified": gps_verified, "gps_distance_m": distance_m,
            "flagged": flagged, "message": message}


@router.post("/{observation_id}/proof")
async def upload_proof(observation_id: int, file: UploadFile = File(...), user_id: str = Form(...),
                       db: Session = Depends(get_db)):
    """Photo de l'étiquette ou du ticket, rattachée à un relevé existant."""
    obs = db.get(PriceObservation, observation_id)
    if not obs:
        raise api_error(404, "observation_not_found", "Relevé introuvable.")
    if obs.user_id != user_id:
        raise api_error(403, "not_owner", "Seul l'auteur du relevé peut ajouter sa preuve.")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
        raise api_error(415, "bad_image", "Format d'image non pris en charge (JPEG, PNG ou WebP).")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise api_error(413, "image_too_large", f"Photo trop lourde (max {settings.max_upload_mb} Mo).")
    obs.proof_image_url = storage.save(data, content_type)
    db.commit()
    return {"id": obs.id, "proof_image_url": obs.proof_image_url}


@router.post("/{observation_id}/vote")
def vote_observation(observation_id: int, payload: VoteCreate, db: Session = Depends(get_db)):
    obs = db.get(PriceObservation, observation_id)
    if not obs:
        raise api_error(404, "observation_not_found", "Relevé introuvable.")
    if obs.user_id == payload.user_id:
        raise api_error(400, "own_observation", "Tu ne peux pas voter pour ton propre relevé.")
    existing = db.scalar(select(ObservationVote).where(
        ObservationVote.observation_id == observation_id,
        ObservationVote.user_id == payload.user_id,
    ))
    if existing:
        existing.vote = payload.vote
        existing.created_at = datetime.now(timezone.utc)
    else:
        db.add(ObservationVote(observation_id=observation_id, user_id=payload.user_id, vote=payload.vote))
    db.commit()
    c, r = pricing.vote_counts(db, [observation_id]).get(observation_id, (0, 0))
    conf = confidence_for(obs.observed_at, c, r, has_proof=bool(obs.proof_image_url),
                          gps_verified=obs.gps_verified, flagged=obs.flagged)
    return {"status": "ok", "confirmations": c, "rejections": r, "my_vote": payload.vote,
            "disputed": pricing.is_disputed(c, r), **conf}
