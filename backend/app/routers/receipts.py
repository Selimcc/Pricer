"""Tickets de caisse : photo -> lignes lues -> validation -> prix publiés.

Parcours :
1. POST /receipts               photo du ticket (+ position) : OCR, analyse, suggestions
2. GET/PATCH /receipts/{id}     l'utilisateur choisit le magasin, corrige, associe les lignes
3. POST /receipts/{id}/publish  chaque ligne associée devient un relevé de prix
                                et le libellé est mémorisé pour les tickets suivants
"""
import re
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models import PriceObservation, Product, Receipt, ReceiptLine, Store
from app.routers.deps import api_error, resolve_product
from app.routers.stores import store_out
from app.schemas import ProductOut
from app.schemas.schemas import USER_ID_PATTERN, ReceiptAction, ReceiptLineUpdate, ReceiptUpdate
from app.services import geo, osm, pricing, ratelimit
from app.services.receipts import matching
from app.services.receipts.ocr import OcrUnavailable, extract_text
from app.services.receipts.parser import ParsedLine, detect_chain, parse_receipt_text, strip_accents
from app.services.storage import ALLOWED_TYPES, private_storage

router = APIRouter(prefix="/receipts", tags=["Tickets de caisse"])

STORE_SEARCH_KM = 1.5


def chain_matches(chain_key: str, store_chain: str) -> bool:
    name = strip_accents(store_chain or "").lower()
    if chain_key == "u":
        return bool(re.search(r"\b(super|hyper)\s?u\b|\bu express\b", name))
    return chain_key in name


def guess_store(db: Session, chain_key: str | None, latitude: float | None, longitude: float | None) -> Store | None:
    if latitude is None or longitude is None:
        return None
    osm.ensure_area_imported(db, latitude, longitude, STORE_SEARCH_KM)
    nearby = geo.stores_within(db, latitude, longitude, STORE_SEARCH_KM, limit=50)
    if chain_key:
        for store, _ in nearby:
            if chain_matches(chain_key, store.chain) or chain_matches(chain_key, store.name):
                return store
    if nearby and nearby[0][1] <= 0.3:
        return nearby[0][0]
    return None


def mapping_chain_key(receipt: Receipt, store: Store | None) -> str:
    if receipt.detected_chain:
        return receipt.detected_chain
    if store:
        return detect_chain(store.chain) or strip_accents(store.chain).lower()
    return ""


def effective_price(line: ReceiptLine) -> Decimal:
    parsed = ParsedLine(line.label, Decimal(line.quantity), Decimal(line.unit_price), Decimal(line.line_total),
                        line.is_weighted, line.discount)
    return parsed.effective_unit_price


def promotion_for(line: ReceiptLine) -> str | None:
    if not line.discount:
        return None
    label = (line.discount_label or "").upper()
    if "FIDEL" in label:
        return "loyalty"
    if "BON" in label or "COUPON" in label:
        return "coupon"
    return "sale"


def receipt_out(db: Session, receipt: Receipt) -> dict:
    lines = db.scalars(select(ReceiptLine).where(ReceiptLine.receipt_id == receipt.id).order_by(ReceiptLine.position)).all()
    products = {p.id: p for p in db.scalars(select(Product).where(
        Product.id.in_([ln.product_id for ln in lines if ln.product_id]))).all()} if lines else {}
    store = db.get(Store, receipt.store_id) if receipt.store_id else None
    lines_sum = sum((Decimal(ln.line_total) - (ln.discount or 0) for ln in lines), Decimal(0))
    warning = None
    if receipt.total and abs(lines_sum - receipt.total) > Decimal("0.05"):
        warning = (f"Les lignes lues font {lines_sum:.2f} € sur un total de {receipt.total:.2f} € : "
                   "certaines lignes ont pu être mal lues.").replace(".", ",")
    elif not lines:
        warning = "Aucune ligne d'article n'a pu être lue. Reprends la photo bien à plat, avec plus de lumière."
    return {
        "id": receipt.id,
        "status": receipt.status,
        "detected_chain": receipt.detected_chain,
        "store": store_out(store) if store else None,
        "purchased_at": receipt.purchased_at,
        "total": float(receipt.total) if receipt.total is not None else None,
        "created_at": receipt.created_at,
        "warning": warning,
        "counts": {
            "lines": len(lines),
            "matched": sum(1 for ln in lines if ln.product_id and ln.status == "pending"),
            "ignored": sum(1 for ln in lines if ln.status == "ignored"),
            "published": sum(1 for ln in lines if ln.status == "published"),
        },
        "lines": [
            {
                "id": ln.id,
                "position": ln.position,
                "label": ln.label,
                "quantity": float(ln.quantity),
                "unit_price": float(ln.unit_price),
                "line_total": float(ln.line_total),
                "discount": float(ln.discount) if ln.discount else None,
                "discount_label": ln.discount_label,
                "effective_unit_price": float(effective_price(ln)),
                "is_weighted": ln.is_weighted,
                "status": ln.status,
                "match_source": ln.match_source,
                "match_score": ln.match_score,
                "product": ProductOut.model_validate(products[ln.product_id]) if ln.product_id in products else None,
            }
            for ln in lines
        ],
    }


def owned_receipt(db: Session, receipt_id: int, user_id: str) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if not receipt or receipt.user_id != user_id:
        raise api_error(404, "receipt_not_found", "Ticket introuvable.")
    return receipt


@router.post("", status_code=201)
async def upload_receipt(
    file: UploadFile = File(...),
    user_id: str = Form(..., pattern=USER_ID_PATTERN),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    db: Session = Depends(get_db),
):
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
        raise api_error(415, "bad_image", "Format d'image non pris en charge (JPEG, PNG ou WebP).")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise api_error(413, "image_too_large", f"Photo trop lourde (max {settings.max_upload_mb} Mo).")
    if not ratelimit.allow(f"receipt:{user_id}", 20):
        raise api_error(429, "rate_limited", "Beaucoup de tickets en peu de temps. Réessaie plus tard.")

    try:
        text = extract_text(data)
    except OcrUnavailable as exc:
        raise api_error(503, "ocr_unavailable", str(exc))
    except Exception:
        raise api_error(422, "unreadable_image", "Impossible de lire cette image. Reprends la photo du ticket.")

    parsed = parse_receipt_text(text)
    receipt = Receipt(
        user_id=user_id,
        detected_chain=parsed.chain_key,
        image_path=private_storage.save(data, content_type),
        raw_text=text[:20000],
        purchased_at=parsed.purchased_at,
        total=parsed.total,
        status="parsed",
    )
    store = guess_store(db, parsed.chain_key, latitude, longitude)
    receipt.store_id = store.id if store else None
    db.add(receipt)
    db.flush()

    catalog = db.scalars(select(Product)).all()
    for i, line in enumerate(parsed.lines):
        product, source, score = (None, None, None) if line.is_weighted else \
            matching.find_match(db, receipt.detected_chain, line.label, catalog)
        db.add(ReceiptLine(
            receipt_id=receipt.id, position=i, label=line.label, quantity=line.quantity,
            unit_price=line.unit_price, line_total=line.line_total, discount=line.discount,
            discount_label=line.discount_label, is_weighted=line.is_weighted,
            product_id=product.id if product else None, match_source=source, match_score=score,
            status="ignored" if line.is_weighted else "pending",
        ))
    db.commit()
    return receipt_out(db, receipt)


@router.get("/{receipt_id}")
def get_receipt(receipt_id: int, user_id: str = Query(..., pattern=USER_ID_PATTERN), db: Session = Depends(get_db)):
    return receipt_out(db, owned_receipt(db, receipt_id, user_id))


@router.patch("/{receipt_id}")
def update_receipt(receipt_id: int, payload: ReceiptUpdate, db: Session = Depends(get_db)):
    receipt = owned_receipt(db, receipt_id, payload.user_id)
    if payload.store_id is not None:
        if not db.get(Store, payload.store_id):
            raise api_error(404, "store_not_found", "Magasin introuvable.")
        receipt.store_id = payload.store_id
    if payload.purchased_at is not None:
        if payload.purchased_at > datetime.now(timezone.utc):
            raise api_error(422, "future_date", "La date d'achat ne peut pas être dans le futur.")
        receipt.purchased_at = payload.purchased_at
    db.commit()
    return receipt_out(db, receipt)


@router.patch("/{receipt_id}/lines/{line_id}")
def update_line(receipt_id: int, line_id: int, payload: ReceiptLineUpdate, db: Session = Depends(get_db)):
    receipt = owned_receipt(db, receipt_id, payload.user_id)
    line = db.get(ReceiptLine, line_id)
    if not line or line.receipt_id != receipt.id:
        raise api_error(404, "line_not_found", "Ligne introuvable.")
    if line.status == "published":
        raise api_error(409, "already_published", "Ce prix est déjà publié.")
    if payload.ean:
        product = resolve_product(db, payload.ean)
        line.product_id, line.match_source, line.match_score = product.id, "user", 1.0
        line.status = "pending"
    if payload.clear_product:
        line.product_id, line.match_source, line.match_score = None, None, None
    if payload.status:
        line.status = payload.status
    if payload.unit_price is not None:
        line.unit_price = payload.unit_price
        line.line_total = (payload.unit_price * Decimal(line.quantity)).quantize(Decimal("0.01"))
    if payload.quantity is not None:
        line.quantity = payload.quantity
        line.line_total = (Decimal(line.unit_price) * payload.quantity).quantize(Decimal("0.01"))
    db.commit()
    return receipt_out(db, receipt)


@router.post("/{receipt_id}/publish")
def publish_receipt(receipt_id: int, payload: ReceiptAction, db: Session = Depends(get_db)):
    receipt = owned_receipt(db, receipt_id, payload.user_id)
    if not receipt.store_id:
        raise api_error(422, "store_required", "Choisis d'abord le magasin du ticket.")
    store = db.get(Store, receipt.store_id)
    chain_key = mapping_chain_key(receipt, store)
    observed_at = receipt.purchased_at or receipt.created_at

    lines = db.scalars(select(ReceiptLine).where(
        ReceiptLine.receipt_id == receipt.id, ReceiptLine.status == "pending",
        ReceiptLine.product_id.is_not(None), ReceiptLine.is_weighted.is_(False),
    )).all()
    published, flagged = 0, 0
    for line in lines:
        price = effective_price(line)
        med, count = pricing.recent_median(db, line.product_id)
        is_flagged = bool(med and count >= 3 and not (0.4 * med <= float(price) <= 2.5 * med))
        promo = promotion_for(line)
        result = db.execute(
            insert(PriceObservation).values(
                product_id=line.product_id, store_id=store.id, user_id=receipt.user_id, price=price,
                is_promotion=promo is not None, promotion_type=promo,
                promotion_label=(line.discount_label or "Promotion").title() if promo else None,
                regular_price=Decimal(line.unit_price) if promo else None,
                proof_image_url=f"receipt:{receipt.id}", gps_verified=False, flagged=is_flagged,
                source="receipt", external_id=f"{receipt.id}:{line.id}", observed_at=observed_at,
            ).on_conflict_do_nothing(constraint="uq_observations_source_external").returning(PriceObservation.id)
        ).first()
        if result:
            line.observation_id = result[0]
        matching.remember(db, chain_key, line.label, line.product_id)
        line.status = "published"
        published += 1
        flagged += int(is_flagged)
    receipt.status = "published"
    db.commit()

    out = receipt_out(db, receipt)
    out["published_now"] = published
    out["message"] = (
        f"{published} prix publié{'s' if published > 1 else ''} grâce à ton ticket. Merci !"
        if published else "Aucune ligne associée à un produit : rien à publier pour l'instant."
    )
    if flagged:
        out["message"] += f" {flagged} prix inhabituel{'s' if flagged > 1 else ''} sera vérifié par la communauté."
    return out


@router.get("", include_in_schema=True)
def list_receipts(user_id: str = Query(..., pattern=USER_ID_PATTERN), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Receipt, Store, func.count(ReceiptLine.id))
        .outerjoin(Store, Store.id == Receipt.store_id)
        .outerjoin(ReceiptLine, ReceiptLine.receipt_id == Receipt.id)
        .where(Receipt.user_id == user_id)
        .group_by(Receipt.id, Store.id)
        .order_by(Receipt.created_at.desc())
        .limit(50)
    ).all()
    return [
        {"id": r.id, "status": r.status, "chain": s.chain if s else r.detected_chain, "store_name": s.name if s else None,
         "purchased_at": r.purchased_at, "created_at": r.created_at,
         "total": float(r.total) if r.total is not None else None, "lines": n}
        for r, s, n in rows
    ]
