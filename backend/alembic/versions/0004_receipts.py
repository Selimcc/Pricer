"""Tickets de caisse : tickets, lignes, mémoire des libellés par enseigne

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("detected_chain", sa.String(100), nullable=True),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_receipts_user_id", "receipts", ["user_id"])

    op.create_table(
        "receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount", sa.Numeric(10, 2), nullable=True),
        sa.Column("discount_label", sa.String(255), nullable=True),
        sa.Column("is_weighted", sa.Boolean(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("match_source", sa.String(20), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("observation_id", sa.Integer(), sa.ForeignKey("price_observations.id"), nullable=True),
    )
    op.create_index("ix_receipt_lines_receipt_id", "receipt_lines", ["receipt_id"])

    op.create_table(
        "receipt_label_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain_key", sa.String(100), nullable=False),
        sa.Column("label_key", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chain_key", "label_key", name="uq_receipt_mapping"),
    )
    op.create_index("ix_receipt_label_mappings_label_key", "receipt_label_mappings", ["label_key"])


def downgrade() -> None:
    op.drop_table("receipt_label_mappings")
    op.drop_table("receipt_lines")
    op.drop_table("receipts")
