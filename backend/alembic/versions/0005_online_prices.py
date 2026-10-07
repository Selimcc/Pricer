"""Prix des sites des enseignes (phase de test) : cache, index des sitemaps, état des sites

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "online_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("retailer", sa.String(30), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("regular_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_promotion", sa.Boolean(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("error", sa.String(255), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("retailer", "product_id", name="uq_online_offer"),
    )
    op.create_index("ix_online_offers_product_id", "online_offers", ["product_id"])

    op.create_table(
        "online_catalog_urls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("retailer", sa.String(30), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("ean", sa.String(32), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("retailer", "url", name="uq_online_catalog_url"),
    )
    op.create_index("ix_online_catalog_urls_retailer", "online_catalog_urls", ["retailer"])
    op.create_index("ix_online_catalog_urls_ean", "online_catalog_urls", ["ean"])

    op.create_table(
        "online_retailer_state",
        sa.Column("retailer", sa.String(30), primary_key=True),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(255), nullable=True),
        sa.Column("sitemap_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("online_retailer_state")
    op.drop_index("ix_online_catalog_urls_ean", "online_catalog_urls")
    op.drop_index("ix_online_catalog_urls_retailer", "online_catalog_urls")
    op.drop_table("online_catalog_urls")
    op.drop_index("ix_online_offers_product_id", "online_offers")
    op.drop_table("online_offers")
