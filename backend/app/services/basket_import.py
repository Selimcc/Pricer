"""Import des prix relevés par la tâche « panier de la semaine ».

Chaque jeudi, cette tâche compare les produits de Selim sur intermarche.com,
carrefour.fr et auchan.fr (navigateur de l'app Claude, à rythme humain, une
quinzaine de produits). Elle envoie ici ce qu'elle a relevé :

    {
      "date": "2026-11-12",
      "zone": {"latitude": 48.947, "longitude": 2.145, "radius_km": 10},
      "stores": {"intermarche": {"city": "Maisons-Laffitte"}},
      "lines": [
        {"line": "Thon, 3 × 140 g", "offers": [
          {"retailer": "intermarche", "ean": "3250391234567", "name": "Thon entier au naturel",
           "brand": "Pâturages", "quantity": "3 x 140 g", "price": 6.27, "regular_price": null,
           "url": "https://www.intermarche.com/produit/..."}
        ]}
      ]
    }

- `price` : prix d'un article tel que vendu (un paquet), pas le total de la semaine.
- Chaque offre devient un prix en ligne (source « online », privée) dans les magasins
  de l'enseigne autour de `zone` ; `stores.<enseigne>.city` limite à la ville du magasin choisi.
- Les offres d'une même ligne deviennent des produits équivalents (groupe « line »).
"""
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import OnlineOffer, Product, ProductGroup, ProductGroupMember
from app.services import catalog, geo
from app.services.ean import normalize_ean
from app.services.online import attach
from app.services.online.retailers import RETAILERS
from app.services.quantity import parse_quantity

MAX_LINES = 80


class BasketImportError(ValueError):
    pass


def _price(value) -> Decimal | None:
    try:
        price = Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return price if Decimal("0.01") <= price <= Decimal("1000") else None


def _product(db: Session, offer: dict) -> tuple[Product | None, bool]:
    """Produit de l'offre (créé si besoin) et s'il est nouveau."""
    ean = normalize_ean(str(offer.get("ean") or ""))
    if not ean:
        return None, False
    product = db.scalar(select(Product).where(Product.ean == ean))
    if product:
        return product, False
    data = catalog.lookup_ean(ean) or {}
    if not data or data.get("name") == catalog.UNNAMED:
        name = (offer.get("name") or "").strip() or f"Produit {ean}"
        value, unit = parse_quantity(offer.get("quantity"))
        data = {**data, "name": name[:255], "brand": data.get("brand") or offer.get("brand"),
                "quantity": data.get("quantity") or offer.get("quantity"),
                "quantity_value": data.get("quantity_value") or value,
                "quantity_unit": data.get("quantity_unit") or unit,
                "source": data.get("source") or "basket"}
    product = Product(ean=ean, **data)
    db.add(product)
    db.flush()
    return product, True


def _group(db: Session, name: str) -> ProductGroup:
    name = " ".join(name.split())[:160]
    group = db.scalar(select(ProductGroup).where(ProductGroup.name == name))
    if not group:
        group = ProductGroup(name=name)
        db.add(group)
        db.flush()
    return group


def import_basket(db: Session, payload: dict) -> dict:
    lines = payload.get("lines")
    zone = payload.get("zone") or {}
    if not isinstance(lines, list) or not lines:
        raise BasketImportError("aucune ligne (« lines ») dans l'envoi")
    if len(lines) > MAX_LINES:
        raise BasketImportError(f"trop de lignes ({len(lines)} > {MAX_LINES})")
    try:
        lat, lon = float(zone["latitude"]), float(zone["longitude"])
    except (KeyError, TypeError, ValueError):
        raise BasketImportError("« zone » doit contenir latitude et longitude") from None
    radius = min(float(zone.get("radius_km") or 10), 30)
    try:
        day = datetime.fromisoformat(str(payload.get("date"))).date()
    except ValueError:
        day = datetime.now(timezone.utc).date()
    checked_at = datetime.combine(day, time(12, 0), tzinfo=timezone.utc)
    store_hints = payload.get("stores") or {}

    stats = {"lines": 0, "offers": 0, "new_products": 0, "skipped": [], "prices_in_stores": 0}
    touched: dict[str, list[Product]] = {}
    for line in lines:
        name = str(line.get("line") or "").strip()
        offers = line.get("offers") or []
        if not name or not offers:
            continue
        stats["lines"] += 1
        group = _group(db, name)
        for offer in offers:
            retailer = str(offer.get("retailer") or "").lower()
            price = _price(offer.get("price"))
            if retailer not in RETAILERS or price is None:
                stats["skipped"].append(f"{name} · {retailer or '?'} : enseigne ou prix invalide")
                continue
            product, created = _product(db, offer)
            if product is None:
                stats["skipped"].append(f"{name} · {retailer} : code-barres absent ou invalide")
                continue
            stats["new_products"] += created
            regular = _price(offer.get("regular_price"))
            promo = regular is not None and regular > price
            row = {"retailer": retailer, "product_id": product.id, "found": True, "price": price,
                   "regular_price": regular if promo else None, "is_promotion": promo,
                   "url": offer.get("url"), "error": None, "checked_at": checked_at}
            stmt = insert(OnlineOffer).values(row)
            db.execute(stmt.on_conflict_do_update(
                constraint="uq_online_offer",
                set_={k: stmt.excluded[k] for k in row if k not in ("retailer", "product_id")}))
            db.execute(insert(ProductGroupMember).values(group_id=group.id, product_id=product.id)
                       .on_conflict_do_nothing(constraint="uq_group_member"))
            touched.setdefault(retailer, []).append(product)
            stats["offers"] += 1
    db.commit()

    # Les prix vont dans les magasins de chaque enseigne autour de la zone
    stores = geo.stores_within(db, lat, lon, radius, limit=500)
    for retailer, products in touched.items():
        r = RETAILERS[retailer]
        chain_stores = [(s, d) for s, d in stores if r.applies_to(s.chain)]
        city = ((store_hints.get(retailer) or {}).get("city") or "").strip().lower()
        if city:
            same_city = [(s, d) for s, d in chain_stores if (s.city or "").strip().lower() == city]
            chain_stores = same_city or chain_stores[:1]
        if not chain_stores:
            stats["skipped"].append(f"{retailer} : aucun magasin de l'enseigne à moins de {radius:g} km")
            continue
        stats["prices_in_stores"] += attach(db, products, chain_stores, retailers={retailer: r},
                                            require_enabled=False)
    return stats
