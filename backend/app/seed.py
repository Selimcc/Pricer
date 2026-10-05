from sqlalchemy import select
from app.db import SessionLocal, engine, Base
from app.models import Product, Store, PriceObservation
from datetime import datetime, timezone, timedelta


DEMO_PRODUCTS = [
    {
        "ean": "3017620422003",
        "name": "Nutella",
        "brand": "Ferrero",
        "quantity": "400 g",
        "image_url": None,
    },
    {
        "ean": "5449000000996",
        "name": "Coca-Cola",
        "brand": "Coca-Cola",
        "quantity": "1.5 L",
        "image_url": None,
    },
]

DEMO_STORES = [
    {
        "chain": "Carrefour",
        "name": "Carrefour Demo",
        "address": "Paris",
        "city": "Paris",
        "latitude": 48.8566,
        "longitude": 2.3522,
    },
    {
        "chain": "Monoprix",
        "name": "Monoprix Demo",
        "address": "Paris",
        "city": "Paris",
        "latitude": 48.8584,
        "longitude": 2.3470,
    },
    {
        "chain": "Auchan",
        "name": "Auchan Demo",
        "address": "Paris",
        "city": "Paris",
        "latitude": 48.8610,
        "longitude": 2.3600,
    },
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        products = {}
        for item in DEMO_PRODUCTS:
            p = db.scalar(select(Product).where(Product.ean == item["ean"]))
            if not p:
                p = Product(**item)
                db.add(p)
                db.flush()
            products[item["ean"]] = p

        stores = []
        for item in DEMO_STORES:
            s = db.scalar(select(Store).where(Store.name == item["name"]))
            if not s:
                s = Store(**item)
                db.add(s)
                db.flush()
            stores.append(s)

        if db.scalar(select(PriceObservation).limit(1)) is None:
            now = datetime.now(timezone.utc)
            demo_prices = [
                (products["3017620422003"], stores[0], 4.89, False, None, 2),
                (products["3017620422003"], stores[1], 4.49, True, "-10% fidélité", 5),
                (products["3017620422003"], stores[2], 4.19, True, "Promotion", 8),
                (products["5449000000996"], stores[0], 2.10, False, None, 1),
                (products["5449000000996"], stores[1], 2.39, False, None, 0),
            ]
            for p, s, price, promo, label, confirmations in demo_prices:
                obs = PriceObservation(
                    product_id=p.id,
                    store_id=s.id,
                    price=price,
                    is_promotion=promo,
                    promotion_label=label,
                    user_id="seed",
                    observed_at=now - timedelta(minutes=confirmations * 7),
                )
                db.add(obs)
                db.flush()

        db.commit()
    finally:
        db.close()
