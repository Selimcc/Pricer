"""Espace personnel : liste de courses et contributions.

L'identité est pour l'instant un identifiant anonyme généré par l'appareil
(pas de compte). Le jour où on ajoute l'authentification, il suffira de
rattacher cet identifiant au compte.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ObservationVote, PriceObservation, Product, ShoppingListItem, Store
from app.routers.deps import api_error, resolve_product, valid_user_id
from app.schemas import ListItemCreate, ListItemUpdate, ProductOut
from app.services import geo, online, osm, pricing
from app.services.providers import sync_product_prices

router = APIRouter(prefix="/users/{user_id}", tags=["Utilisateur"])

LEVELS = [
    (0, "Nouveau venu"),
    (3, "Éclaireur"),
    (15, "Pilier du quartier"),
    (50, "Légende du rayon"),
]


def level_for(count: int) -> dict:
    current, nxt = LEVELS[0], None
    for i, (threshold, name) in enumerate(LEVELS):
        if count >= threshold:
            current = (threshold, name)
            nxt = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    return {"name": current[1], "next_name": nxt[1] if nxt else None,
            "next_at": nxt[0] if nxt else None, "progress": (count - current[0]) / (nxt[0] - current[0]) if nxt else 1.0}


# --- Liste de courses ---------------------------------------------------

def _list_items(db: Session, user_id: str):
    return db.execute(
        select(ShoppingListItem, Product)
        .join(Product, Product.id == ShoppingListItem.product_id)
        .where(ShoppingListItem.user_id == user_id)
        .order_by(ShoppingListItem.checked, ShoppingListItem.added_at.desc())
    ).all()


def _item_out(item: ShoppingListItem, product: Product) -> dict:
    return {"id": item.id, "quantity": item.quantity, "checked": item.checked, "added_at": item.added_at,
            "product": ProductOut.model_validate(product)}


@router.get("/list")
def get_list(user_id: str = Depends(valid_user_id), db: Session = Depends(get_db)):
    return [_item_out(i, p) for i, p in _list_items(db, user_id)]


@router.post("/list", status_code=201)
def add_to_list(payload: ListItemCreate, user_id: str = Depends(valid_user_id), db: Session = Depends(get_db)):
    product = resolve_product(db, payload.ean)
    item = db.scalar(select(ShoppingListItem).where(
        ShoppingListItem.user_id == user_id, ShoppingListItem.product_id == product.id))
    if item:
        item.quantity = min(99, item.quantity + payload.quantity)
        item.checked = False
    else:
        if db.scalar(select(func.count()).where(ShoppingListItem.user_id == user_id)) >= 150:
            raise api_error(400, "list_full", "Ta liste est pleine (150 produits).")
        item = ShoppingListItem(user_id=user_id, product_id=product.id, quantity=payload.quantity)
        db.add(item)
    db.commit()
    db.refresh(item)
    return _item_out(item, product)


@router.patch("/list/{item_id}")
def update_list_item(item_id: int, payload: ListItemUpdate, user_id: str = Depends(valid_user_id),
                     db: Session = Depends(get_db)):
    item = db.get(ShoppingListItem, item_id)
    if not item or item.user_id != user_id:
        raise api_error(404, "item_not_found", "Article introuvable.")
    if payload.quantity is not None:
        item.quantity = payload.quantity
    if payload.checked is not None:
        item.checked = payload.checked
    db.commit()
    return _item_out(item, db.get(Product, item.product_id))


@router.delete("/list/{item_id}", status_code=204)
def delete_list_item(item_id: int, user_id: str = Depends(valid_user_id), db: Session = Depends(get_db)):
    item = db.get(ShoppingListItem, item_id)
    if not item or item.user_id != user_id:
        raise api_error(404, "item_not_found", "Article introuvable.")
    db.delete(item)
    db.commit()


@router.delete("/list", status_code=204)
def clear_checked(user_id: str = Depends(valid_user_id), db: Session = Depends(get_db)):
    for item in db.scalars(select(ShoppingListItem).where(
            ShoppingListItem.user_id == user_id, ShoppingListItem.checked.is_(True))).all():
        db.delete(item)
    db.commit()


@router.get("/list/comparison")
def compare_list(
    user_id: str = Depends(valid_user_id),
    latitude: float = Query(48.8566, ge=-90, le=90),
    longitude: float = Query(2.3522, ge=-180, le=180),
    radius_km: float = Query(10, gt=0, le=50),
    db: Session = Depends(get_db),
):
    """« Avec ma liste, je vais où ? »

    Pour chaque magasin : total des produits dont on connaît le prix, et
    total estimé (les produits manquants sont comptés au prix moyen du
    secteur) pour que des magasins avec une couverture différente restent
    comparables. Les produits sans aucun prix dans le secteur sont listés à part.
    """
    entries = [(i, p) for i, p in _list_items(db, user_id) if not i.checked]
    if not entries:
        return {"stores": [], "priced_items": 0, "unpriced": [], "total_items": 0, "split": None}

    osm.ensure_area_imported(db, latitude, longitude, radius_km)
    products = [p for _, p in entries]
    for p in products:
        sync_product_prices(db, p)
    qty = {p.id: i.quantity for i, p in entries}
    stores = geo.stores_within(db, latitude, longitude, radius_km)
    # Prix en ligne déjà connus (pas de requête vers les sites ici : la liste peut être longue)
    online.attach(db, products, stores)
    rows = pricing.current_prices(db, products, stores)
    by_store = pricing.group_by_store(rows)

    prices_by_product: dict[int, list[float]] = {}
    for (pid, _), row in rows.items():
        prices_by_product.setdefault(pid, []).append(row["price"])
    avg = {pid: sum(v) / len(v) for pid, v in prices_by_product.items()}
    priced = [p for p in products if p.id in avg]
    unpriced = [p for p in products if p.id not in avg]

    store_by_id = {s.id: (s, d) for s, d in stores}
    results = []
    for store_id, items in by_store.items():
        store, distance = store_by_id[store_id]
        known = sum(r["price"] * qty[pid] for pid, r in items.items())
        missing = [p for p in priced if p.id not in items]
        estimated = known + sum(avg[p.id] * qty[p.id] for p in missing)
        results.append({
            "store_id": store.id,
            "store_name": store.name,
            "chain": store.chain,
            "city": store.city,
            "latitude": store.latitude,
            "longitude": store.longitude,
            "distance_km": distance,
            "covered": len(items),
            "coverage": round(len(items) / len(priced), 2) if priced else 0,
            "known_total": round(known, 2),
            "estimated_total": round(estimated, 2),
            "missing": [{"ean": p.ean, "name": p.name} for p in missing],
            "lines": [
                {"ean": next(p.ean for p in products if p.id == pid), "price": r["price"],
                 "quantity": qty[pid], "is_promotion": r["is_promotion"],
                 "confidence_level": r["confidence_level"]}
                for pid, r in items.items()
            ],
        })

    # Les magasins qui couvrent au moins la moitié de la liste passent devant.
    results.sort(key=lambda r: (r["coverage"] < 0.5, r["estimated_total"], r["distance_km"]))
    if results:
        best = results[0]["estimated_total"]
        for r in results:
            r["extra_vs_best"] = round(r["estimated_total"] - best, 2)

    # Option « je fais plusieurs magasins » : le moins cher pour chaque produit.
    split_total, split_stores = 0.0, set()
    for p in priced:
        candidates = [(r["price"], sid) for (pid, sid), r in rows.items() if pid == p.id]
        price, sid = min(candidates)
        split_total += price * qty[p.id]
        split_stores.add(sid)

    return {
        "stores": results[:10],
        "total_items": len(products),
        "priced_items": len(priced),
        "unpriced": [{"ean": p.ean, "name": p.name} for p in unpriced],
        "split": {"total": round(split_total, 2), "store_count": len(split_stores)} if priced else None,
        "max_savings": round(results[-1]["estimated_total"] - results[0]["estimated_total"], 2) if len(results) > 1 else 0,
    }


# --- Contributions ------------------------------------------------------

@router.get("/contributions")
def contributions(user_id: str = Depends(valid_user_id), limit: int = Query(20, ge=1, le=100),
                  db: Session = Depends(get_db)):
    my_obs = select(PriceObservation.id).where(PriceObservation.user_id == user_id)
    count = db.scalar(select(func.count()).where(PriceObservation.user_id == user_id)) or 0
    confirmations = db.scalar(select(func.count()).where(
        ObservationVote.observation_id.in_(my_obs), ObservationVote.vote == 1)) or 0
    votes_cast = db.scalar(select(func.count()).where(ObservationVote.user_id == user_id)) or 0
    stores = db.scalar(select(func.count(func.distinct(PriceObservation.store_id))).where(
        PriceObservation.user_id == user_id)) or 0
    with_proof = db.scalar(select(func.count()).where(
        PriceObservation.user_id == user_id, PriceObservation.proof_image_url.is_not(None))) or 0

    products_added = db.scalar(select(func.count()).where(Product.created_by == user_id)) or 0
    photos_added = db.scalar(select(func.count()).where(Product.image_added_by == user_id)) or 0

    recent = db.execute(
        select(PriceObservation, Product, Store)
        .join(Product, Product.id == PriceObservation.product_id)
        .join(Store, Store.id == PriceObservation.store_id)
        .where(PriceObservation.user_id == user_id)
        .order_by(PriceObservation.observed_at.desc())
        .limit(limit)
    ).all()
    votes = pricing.vote_counts(db, [o.id for o, _, _ in recent])
    score = count + votes_cast // 3 + with_proof + 2 * products_added + photos_added
    return {
        "user_id": user_id,
        "price_count": count,
        "confirmations_received": confirmations,
        "votes_cast": votes_cast,
        "store_count": stores,
        "proof_count": with_proof,
        "products_added": products_added,
        "photos_added": photos_added,
        "score": score,
        "level": level_for(score),
        "recent": [
            {"id": o.id, "ean": p.ean, "product": p.name, "image_url": p.image_url, "chain": s.chain,
             "store": s.name, "price": float(o.price), "observed_at": o.observed_at,
             "is_promotion": o.is_promotion, "has_proof": bool(o.proof_image_url),
             "confirmations": votes.get(o.id, (0, 0))[0], "rejections": votes.get(o.id, (0, 0))[1]}
            for o, p, s in recent
        ],
    }
