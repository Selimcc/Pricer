"""Tests sur une vraie base PostgreSQL + PostGIS.

Base utilisée : TEST_DATABASE_URL (par défaut grocery_test en local).
Elle est entièrement vidée au début de la session. Les appels réseau
(Open Food Facts, Open Prices, Overpass) sont désactivés ; les tests qui
en ont besoin remplacent les fonctions de récupération.
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://grocery:grocery_dev_password@localhost:5432/grocery_test"
)
os.environ.update({
    "DATABASE_URL": TEST_DB,
    "SEED_DEMO": "false",
    "ENABLE_OPENFOODFACTS": "false",
    "ENABLE_OPEN_PRICES": "false",
    "ENABLE_OSM_IMPORT": "false",
    "UPLOAD_DIR": tempfile.mkdtemp(prefix="pricer-uploads-"),
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.migrate import upgrade_database  # noqa: E402
from app.models import PriceObservation, Product, Store  # noqa: E402
from app.services import ratelimit  # noqa: E402

TABLES = "observation_votes, price_observations, shopping_list_items, osm_import_areas, stores, products"

# Maisons-Laffitte, pour des distances réalistes
HOME = (48.9470, 2.1450)


@pytest.fixture(scope="session", autouse=True)
def database():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    upgrade_database()
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    ratelimit.reset()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def factory(db):
    class Factory:
        def product(self, ean="3017620422003", name="Nutella", quantity_value=400, quantity_unit="g", **kw):
            p = Product(ean=ean, name=name, brand=kw.pop("brand", "Ferrero"), quantity=kw.pop("quantity", "400 g"),
                        quantity_value=Decimal(quantity_value) if quantity_value else None,
                        quantity_unit=quantity_unit, source=kw.pop("source", "off"), **kw)
            db.add(p)
            db.commit()
            return p

        def store(self, chain="Carrefour", lat=HOME[0], lon=HOME[1], **kw):
            s = Store(chain=chain, name=kw.pop("name", f"{chain} test"), city=kw.pop("city", "Maisons-Laffitte"),
                      latitude=lat, longitude=lon, source=kw.pop("source", "osm"), **kw)
            db.add(s)
            db.commit()
            return s

        def price(self, product, store, price, days_ago=0.0, user_id="alice", **kw):
            o = PriceObservation(
                product_id=product.id, store_id=store.id, price=Decimal(str(price)), user_id=user_id,
                is_promotion=kw.pop("is_promotion", False), source=kw.pop("source", "community"),
                observed_at=datetime.now(timezone.utc) - timedelta(days=days_ago), **kw,
            )
            db.add(o)
            db.commit()
            return o

    return Factory()
