"""Rapprochement « libellé de ticket » -> produit du catalogue.

1. Mémoire collective : ce libellé a déjà été associé chez cette enseigne
   (ou ailleurs) par un utilisateur -> association directe.
2. Sinon, ressemblance avec les noms du catalogue. Les tickets abrègent
   (« LAIT DEMI ECR LACTEL ») : un mot compte s'il est le début de l'autre.
   Le résultat n'est qu'une suggestion que l'utilisateur confirme.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Product, ReceiptLabelMapping
from app.services.receipts.parser import strip_accents

STOP = {"DE", "DU", "LA", "LE", "LES", "ET", "AU", "AUX", "EN", "X", "A", "D", "L"}
SUGGEST_THRESHOLD = 0.6


def label_key(label: str) -> str:
    s = strip_accents(label.upper())
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    s = re.sub(r"[^A-Z0-9.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:255]


def tokens(text: str) -> list[str]:
    return [t for t in label_key(text).split() if t not in STOP and len(t) >= 2]


def _token_match(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 3 and long_.startswith(short)


def similarity(label: str, product: Product) -> float:
    lt = tokens(label)
    pt = tokens(" ".join(x for x in (product.name, product.brand, product.quantity) if x))
    if not lt or not pt:
        return 0.0
    matched = [t for t in lt if any(_token_match(t, p) for p in pt)]
    if not any(len(t) >= 4 and not t[0].isdigit() for t in matched):
        return 0.0  # au moins un vrai mot en commun, pas seulement « 1.5L »
    return len(matched) / len(lt)


def find_match(db: Session, chain_key: str | None, label: str, catalog: list[Product] | None = None):
    """-> (product, source, score) ou (None, None, None)."""
    key = label_key(label)
    mapping = db.scalar(
        select(ReceiptLabelMapping)
        .where(ReceiptLabelMapping.label_key == key)
        .order_by((ReceiptLabelMapping.chain_key == (chain_key or "")).desc(), ReceiptLabelMapping.uses.desc())
        .limit(1)
    )
    if mapping:
        product = db.get(Product, mapping.product_id)
        same_chain = mapping.chain_key == (chain_key or "")
        return product, "mapping", 1.0 if same_chain else 0.9

    # Catalogue entier pour le prototype ; à remplacer par un index trigrammes (pg_trgm) à grande échelle
    candidates = catalog if catalog is not None else db.scalars(select(Product)).all()
    best, best_score = None, 0.0
    for product in candidates:
        score = similarity(label, product)
        if score > best_score:
            best, best_score = product, score
    if best and best_score >= SUGGEST_THRESHOLD:
        return best, "fuzzy", round(best_score, 2)
    return None, None, None


def remember(db: Session, chain_key: str | None, label: str, product_id: int) -> None:
    stmt = insert(ReceiptLabelMapping).values(
        chain_key=chain_key or "", label_key=label_key(label), product_id=product_id, uses=1,
        updated_at=datetime.now(timezone.utc),
    )
    db.execute(stmt.on_conflict_do_update(
        constraint="uq_receipt_mapping",
        set_={"product_id": stmt.excluded.product_id, "uses": ReceiptLabelMapping.uses + 1,
              "updated_at": stmt.excluded.updated_at},
    ))
