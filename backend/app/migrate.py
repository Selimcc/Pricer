"""Met la base à jour au démarrage du conteneur.

Les bases créées avant la V0.4 (par create_all, sans Alembic) sont
reconnues et « tamponnées » en révision 0001 : leurs données sont
conservées puis migrées normalement.

Usage : python -m app.migrate
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.db import engine as default_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent


def upgrade_database(engine: Engine | None = None) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    with (engine or default_engine).begin() as connection:
        cfg.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "products" in tables and "alembic_version" not in tables:
            print("[migrate] Base V0.2 détectée : marquage en révision 0001 avant migration.")
            command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")


def main() -> None:
    upgrade_database()
    from app.core.config import settings
    from app.seed import seed

    if settings.seed_demo:
        seed()
    print("[migrate] Base à jour.")


if __name__ == "__main__":
    main()
