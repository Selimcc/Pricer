"""V0.4 : vraies sources, PostGIS, liste de courses, preuves

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

STORE_GEOG = "geography(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326))"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # --- products -------------------------------------------------------
    op.add_column("products", sa.Column("quantity_value", sa.Numeric(10, 3), nullable=True))
    op.add_column("products", sa.Column("quantity_unit", sa.String(8), nullable=True))
    op.add_column("products", sa.Column("nutriscore_grade", sa.String(2), nullable=True))
    op.add_column("products", sa.Column("source", sa.String(20), nullable=False, server_default="off"))
    op.add_column("products", sa.Column("prices_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()))

    # --- stores ---------------------------------------------------------
    op.alter_column("stores", "address", nullable=True)
    op.alter_column("stores", "city", nullable=True)
    op.add_column("stores", sa.Column("postcode", sa.String(10), nullable=True))
    op.add_column("stores", sa.Column("osm_type", sa.String(10), nullable=True))
    op.add_column("stores", sa.Column("osm_id", sa.BigInteger(), nullable=True))
    op.add_column("stores", sa.Column("shop_type", sa.String(40), nullable=True))
    op.add_column("stores", sa.Column("source", sa.String(20), nullable=False, server_default="demo"))
    op.create_unique_constraint("uq_stores_osm", "stores", ["osm_type", "osm_id"])
    # Index géographique : les requêtes « magasins à moins de X km » passent par lui.
    op.execute(f"CREATE INDEX ix_stores_geog ON stores USING gist (({STORE_GEOG}))")

    # --- price_observations --------------------------------------------
    op.add_column("price_observations", sa.Column("promotion_type", sa.String(20), nullable=True))
    op.add_column("price_observations", sa.Column("regular_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_observations", sa.Column("gps_distance_m", sa.Float(), nullable=True))
    op.add_column("price_observations", sa.Column("gps_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("price_observations", sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("price_observations", sa.Column("source", sa.String(20), nullable=False, server_default="community"))
    op.add_column("price_observations", sa.Column("external_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_observations_source_external", "price_observations", ["source", "external_id"])
    op.create_index("ix_observations_product_store_date", "price_observations", ["product_id", "store_id", "observed_at"])

    # Reprise des données existantes
    op.execute("UPDATE price_observations SET source = 'demo' WHERE user_id = 'seed'")
    op.execute(
        "UPDATE price_observations SET promotion_type = CASE "
        "WHEN promotion_label ILIKE '%fid%' THEN 'loyalty' ELSE 'sale' END "
        "WHERE is_promotion"
    )

    # --- observation_votes : un seul vote par personne et par relevé ----
    op.execute(
        "DELETE FROM observation_votes a USING observation_votes b "
        "WHERE a.observation_id = b.observation_id AND a.user_id = b.user_id AND a.id < b.id"
    )
    op.create_unique_constraint("uq_votes_observation_user", "observation_votes", ["observation_id", "user_id"])

    # --- nouvelles tables ----------------------------------------------
    op.create_table(
        "osm_import_areas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius_km", sa.Float(), nullable=False),
        sa.Column("store_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "shopping_list_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "product_id", name="uq_list_user_product"),
    )
    op.create_index("ix_shopping_list_items_user_id", "shopping_list_items", ["user_id"])


def downgrade() -> None:
    op.drop_table("shopping_list_items")
    op.drop_table("osm_import_areas")
    op.drop_constraint("uq_votes_observation_user", "observation_votes")
    op.drop_index("ix_observations_product_store_date", "price_observations")
    op.drop_constraint("uq_observations_source_external", "price_observations")
    for col in ("external_id", "source", "flagged", "gps_verified", "gps_distance_m", "regular_price", "promotion_type"):
        op.drop_column("price_observations", col)
    op.execute("DROP INDEX IF EXISTS ix_stores_geog")
    op.drop_constraint("uq_stores_osm", "stores")
    for col in ("source", "shop_type", "osm_id", "osm_type", "postcode"):
        op.drop_column("stores", col)
    for col in ("created_at", "prices_synced_at", "source", "nutriscore_grade", "quantity_unit", "quantity_value"):
        op.drop_column("products", col)
