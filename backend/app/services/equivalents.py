"""Produits équivalents (même ligne de courses, enseignes différentes)."""
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models import Product, ProductGroup, ProductGroupMember, Store
from app.services import pricing


def equivalents_of(db: Session, product_ids: list[int]) -> dict[int, list[tuple[Product, str]]]:
    """produit -> [(produit équivalent, nom du groupe)], sans le produit lui-même."""
    if not product_ids:
        return {}
    mine, other = aliased(ProductGroupMember), aliased(ProductGroupMember)
    rows = db.execute(
        select(mine.product_id, Product, ProductGroup.name)
        .join(other, other.group_id == mine.group_id)
        .join(Product, Product.id == other.product_id)
        .join(ProductGroup, ProductGroup.id == mine.group_id)
        .where(mine.product_id.in_(product_ids), other.product_id != mine.product_id)
    ).all()
    result: dict[int, list[tuple[Product, str]]] = {}
    for pid, product, group in rows:
        if all(p.id != product.id for p, _ in result.get(pid, [])):
            result.setdefault(pid, []).append((product, group))
    return result


def with_substitutes(db: Session, products: list[Product], stores: list[tuple[Store, float | None]],
                     rows: dict[tuple[int, int], dict]) -> dict[tuple[int, int], dict]:
    """Complète les prix : là où un produit n'a pas de prix, le moins cher de ses équivalents.

    La ligne ajoutée porte `substitute` (le produit pris à la place).
    """
    equiv = equivalents_of(db, [p.id for p in products])
    members = {m.id: m for options in equiv.values() for m, _ in options}
    if not members:
        return rows
    member_rows = pricing.current_prices(db, list(members.values()), stores)
    result = dict(rows)
    for p in products:
        for store, _ in stores:
            if (p.id, store.id) in result:
                continue
            candidates = [(member_rows[(m.id, store.id)], m) for m, _ in equiv.get(p.id, [])
                          if (m.id, store.id) in member_rows]
            if candidates:
                row, m = min(candidates, key=lambda c: c[0]["price"])
                result[(p.id, store.id)] = {**row, "substitute": {
                    "ean": m.ean, "name": m.name, "brand": m.brand, "quantity": m.quantity}}
    return result


def best_equivalent_prices(db: Session, product: Product, stores: list[tuple[Store, float | None]]) -> list[dict]:
    """Pour la fiche produit : le meilleur prix de chaque équivalent autour de l'utilisateur."""
    options = equivalents_of(db, [product.id]).get(product.id, [])
    if not options:
        return []
    rows = pricing.current_prices(db, [m for m, _ in options], stores)
    out = []
    for m, group in options:
        priced = [r for (pid, _), r in rows.items() if pid == m.id]
        if not priced:
            continue
        best = min(priced, key=lambda r: (r["price"], r["distance_km"] or 0))
        out.append({
            "group": group,
            "product": {"ean": m.ean, "name": m.name, "brand": m.brand, "quantity": m.quantity,
                        "image_url": m.image_url},
            "price": best["price"], "unit_price": best.get("unit_price"),
            "unit_price_label": best.get("unit_price_label"), "chain": best["chain"],
            "store_name": best["store_name"], "distance_km": best["distance_km"],
            "source_label": best["source_label"], "observed_at": best["observed_at"],
        })
    return sorted(out, key=lambda e: e["price"])
