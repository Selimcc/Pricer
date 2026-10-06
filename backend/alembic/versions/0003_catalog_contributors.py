"""Catalogue maison : qui a ajouté le produit, qui a ajouté sa photo

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("created_by", sa.String(100), nullable=True))
    op.add_column("products", sa.Column("image_added_by", sa.String(100), nullable=True))
    op.create_index("ix_products_created_by", "products", ["created_by"])
    op.create_index("ix_products_image_added_by", "products", ["image_added_by"])


def downgrade() -> None:
    op.drop_index("ix_products_image_added_by", "products")
    op.drop_index("ix_products_created_by", "products")
    op.drop_column("products", "image_added_by")
    op.drop_column("products", "created_by")
