from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


# Valeurs autorisées (gardées en String plutôt qu'en ENUM Postgres pour
# pouvoir en ajouter sans migration lourde).
PRICE_SOURCES = ("community", "open_prices", "demo")
PROMOTION_TYPES = ("sale", "loyalty", "multi_buy", "bundle", "clearance", "coupon", "other")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ean: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Quantité normalisée pour le prix au kilo / litre / unité
    quantity_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)  # g | ml | unit
    nutriscore_grade: Mapped[str | None] = mapped_column(String(2), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="off", server_default="off")
    prices_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=True)


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("osm_type", "osm_id", name="uq_stores_osm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    osm_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # node | way | relation
    osm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    shop_type: Mapped[str | None] = mapped_column(String(40), nullable=True)  # supermarket, convenience…
    source: Mapped[str] = mapped_column(String(20), default="demo", server_default="demo")


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_observations_source_external"),
        Index("ix_observations_product_store_date", "product_id", "store_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(100), default="demo-user")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_promotion: Mapped[bool] = mapped_column(Boolean, default=False)
    promotion_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    promotion_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regular_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    proof_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    source: Mapped[str] = mapped_column(String(20), default="community", server_default="community")
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ObservationVote(Base):
    __tablename__ = "observation_votes"
    __table_args__ = (UniqueConstraint("observation_id", "user_id", name="uq_votes_observation_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("price_observations.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(100))
    vote: Mapped[int] = mapped_column(Integer)  # +1 confirmé, -1 incorrect
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OsmImportArea(Base):
    """Zones déjà importées depuis OpenStreetMap (évite de rappeler Overpass)."""

    __tablename__ = "osm_import_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float)
    store_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_list_user_product"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
