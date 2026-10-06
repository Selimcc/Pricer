"""Schéma initial (identique à la V0.2, créée à l'époque par create_all)

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ean", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("quantity", sa.String(100), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
    )
    op.create_index("ix_products_ean", "products", ["ean"], unique=True)

    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
    )
    op.create_index("ix_stores_chain", "stores", ["chain"])

    op.create_table(
        "price_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_promotion", sa.Boolean(), nullable=False),
        sa.Column("promotion_label", sa.String(255), nullable=True),
        sa.Column("proof_image_url", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_observations_product_id", "price_observations", ["product_id"])
    op.create_index("ix_price_observations_store_id", "price_observations", ["store_id"])
    op.create_index("ix_price_observations_observed_at", "price_observations", ["observed_at"])

    op.create_table(
        "observation_votes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("observation_id", sa.Integer(), sa.ForeignKey("price_observations.id"), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("vote", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_observation_votes_observation_id", "observation_votes", ["observation_id"])


def downgrade() -> None:
    op.drop_table("observation_votes")
    op.drop_table("price_observations")
    op.drop_table("stores")
    op.drop_table("products")
