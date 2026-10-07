"""Une base V0.2 (créée par create_all, sans Alembic) doit migrer sans perte."""
import os
import uuid

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.migrate import upgrade_database
from tests.conftest import TEST_DB


def test_v02_database_is_migrated_without_data_loss():
    name = f"pricer_migr_{uuid.uuid4().hex[:8]}"
    admin = create_engine(make_url(TEST_DB).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    engine = create_engine(make_url(TEST_DB).set(database=name))
    try:
        # 1. Base « V0.2 » : schéma 0001 puis suppression de la trace Alembic
        upgrade_database_to_0001(engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE alembic_version"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.execute(text("INSERT INTO products (ean, name) VALUES ('3254381025887', 'Mon produit scanné')"))
            conn.execute(text("INSERT INTO stores (chain, name, address, city, latitude, longitude) "
                              "VALUES ('Monoprix', 'Monoprix Demo', 'Paris', 'Paris', 48.85, 2.34)"))
            conn.execute(text("INSERT INTO price_observations (product_id, store_id, user_id, price, is_promotion, "
                              "promotion_label, observed_at) VALUES (1, 1, 'seed', 4.49, true, '-10% fidélité', now())"))
            for _ in range(2):  # doublon de vote (impossible à partir de la V0.4)
                conn.execute(text("INSERT INTO observation_votes (observation_id, user_id, vote, created_at) "
                                  "VALUES (1, 'bob', 1, now())"))

        # 2. Démarrage V0.4
        upgrade_database(engine)

        with engine.connect() as conn:
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
            assert conn.scalar(text("SELECT name FROM products WHERE ean = '3254381025887'")) == "Mon produit scanné"
            row = conn.execute(text("SELECT source, promotion_type FROM price_observations")).one()
            assert tuple(row) == ("demo", "loyalty")
            assert conn.scalar(text("SELECT count(*) FROM observation_votes")) == 1
            assert conn.scalar(text("SELECT source FROM stores")) == "demo"
        assert "shopping_list_items" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
        admin.dispose()


def upgrade_database_to_0001(engine):
    from alembic import command
    from alembic.config import Config

    from app.migrate import BACKEND_DIR

    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001")
