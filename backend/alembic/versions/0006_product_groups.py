"""Produits équivalents entre enseignes (marques distributeur)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "product_group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("product_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", "product_id", name="uq_group_member"),
    )
    op.create_index("ix_product_group_members_group_id", "product_group_members", ["group_id"])
    op.create_index("ix_product_group_members_product_id", "product_group_members", ["product_id"])


def downgrade() -> None:
    op.drop_table("product_group_members")
    op.drop_table("product_groups")
