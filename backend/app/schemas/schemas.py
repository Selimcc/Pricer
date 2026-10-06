from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.services.catalog import FAMILIES

USER_ID_PATTERN = r"^[A-Za-z0-9_\-:.]{3,100}$"

PromotionType = Literal["sale", "loyalty", "multi_buy", "bundle", "clearance", "coupon", "other"]


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ean: str
    name: str
    brand: str | None = None
    quantity: str | None = None
    image_url: str | None = None
    quantity_value: Decimal | None = None
    quantity_unit: str | None = None
    nutriscore_grade: str | None = None
    source: str | None = None

    @computed_field
    @property
    def family(self) -> str | None:
        return FAMILIES.get(self.source or "")

    @computed_field
    @property
    def needs_photo(self) -> bool:
        """Fiche incomplète : la communauté peut ajouter la photo."""
        return not self.image_url


class ProductCreate(BaseModel):
    """Produit absent d'Open Food Facts, saisi par un utilisateur."""

    ean: str
    name: str = Field(min_length=2, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    quantity: str | None = Field(default=None, max_length=100)
    user_id: str | None = Field(default=None, pattern=USER_ID_PATTERN)


class ObservationCreate(BaseModel):
    ean: str
    store_id: int
    price: Decimal = Field(gt=Decimal("0.04"), lt=Decimal("1000"), decimal_places=2)
    is_promotion: bool = False
    promotion_type: PromotionType | None = None
    promotion_label: str | None = Field(default=None, max_length=255)
    regular_price: Decimal | None = Field(default=None, gt=0, lt=Decimal("1000"), decimal_places=2)
    user_id: str = Field(default="demo-user", pattern=USER_ID_PATTERN)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    proof_image_url: str | None = None


class VoteCreate(BaseModel):
    user_id: str = Field(default="demo-user", pattern=USER_ID_PATTERN)
    vote: Literal[-1, 1]


class ListItemCreate(BaseModel):
    ean: str
    quantity: int = Field(default=1, ge=1, le=99)


class ListItemUpdate(BaseModel):
    quantity: int | None = Field(default=None, ge=1, le=99)
    checked: bool | None = None


class ReceiptUpdate(BaseModel):
    user_id: str = Field(pattern=USER_ID_PATTERN)
    store_id: int | None = None
    purchased_at: datetime | None = None


class ReceiptLineUpdate(BaseModel):
    user_id: str = Field(pattern=USER_ID_PATTERN)
    ean: str | None = None
    clear_product: bool = False
    status: Literal["pending", "ignored"] | None = None
    unit_price: Decimal | None = Field(default=None, gt=0, lt=Decimal("1000"), decimal_places=2)
    quantity: Decimal | None = Field(default=None, gt=0, lt=Decimal("1000"))


class ReceiptAction(BaseModel):
    user_id: str = Field(pattern=USER_ID_PATTERN)
