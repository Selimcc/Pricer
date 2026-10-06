"""Données de démonstration (désactivables avec SEED_DEMO=false).

Magasins fictifs dans Paris centre, prix fictifs : ils sont marqués
source = "demo" et l'application les affiche comme tels.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import PriceObservation, Product, Store

DEMO_PRODUCTS = [
    {"ean": "3017620422003", "name": "Nutella", "brand": "Ferrero", "quantity": "400 g",
     "quantity_value": Decimal(400), "quantity_unit": "g", "nutriscore_grade": "e"},
    {"ean": "5449000000996", "name": "Coca-Cola", "brand": "Coca-Cola", "quantity": "1.5 L",
     "quantity_value": Decimal(1500), "quantity_unit": "ml", "nutriscore_grade": "e"},
]

DEMO_STORES = [
    {"chain": "Carrefour", "name": "Carrefour Demo", "address": "Paris", "city": "Paris",
     "latitude": 48.8566, "longitude": 2.3522},
    {"chain": "Monoprix", "name": "Monoprix Demo", "address": "Paris", "city": "Paris",
     "latitude": 48.8584, "longitude": 2.3470},
    {"chain": "Auchan", "name": "Auchan Demo", "address": "Paris", "city": "Paris",
     "latitude": 48.8610, "longitude": 2.3600},
]


def seed() -> None:
    db = SessionLocal()
    try:
        products = {}
        for item in DEMO_PRODUCTS:
            p = db.scalar(select(Product).where(Product.ean == item["ean"]))
            if not p:
                p = Product(**item, source="demo")
                db.add(p)
                db.flush()
            elif p.quantity_value is None:
                p.quantity_value, p.quantity_unit = item["quantity_value"], item["quantity_unit"]
            products[item["ean"]] = p

        stores = []
        for item in DEMO_STORES:
            s = db.scalar(select(Store).where(Store.name == item["name"]))
            if not s:
                s = Store(**item, source="demo")
                db.add(s)
                db.flush()
            stores.append(s)

        if db.scalar(select(PriceObservation).where(PriceObservation.source == "demo").limit(1)) is None:
            now = datetime.now(timezone.utc)
            demo_prices = [
                ("3017620422003", 0, "4.89", False, None, None, 2),
                ("3017620422003", 1, "4.49", True, "loyalty", "-10% fidélité", 5),
                ("3017620422003", 2, "4.19", True, "sale", "Promotion", 8),
                ("5449000000996", 0, "2.10", False, None, None, 1),
                ("5449000000996", 1, "2.39", False, None, None, 0),
            ]
            for ean, store_idx, price, promo, promo_type, label, minutes in demo_prices:
                db.add(PriceObservation(
                    product_id=products[ean].id, store_id=stores[store_idx].id,
                    price=Decimal(price), is_promotion=promo, promotion_type=promo_type,
                    promotion_label=label, user_id="seed", source="demo",
                    observed_at=now - timedelta(minutes=minutes * 7),
                ))
        db.commit()
    finally:
        db.close()
