from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    id: int
    ean: str
    name: str
    brand: str | None = None
    quantity: str | None = None
    image_url: str | None = None

    class Config:
        from_attributes = True


class ObservationCreate(BaseModel):
    ean: str
    store_id: int
    price: Decimal = Field(gt=0)
    is_promotion: bool = False
    promotion_label: str | None = None
    user_id: str = "demo-user"
    latitude: float | None = None
    longitude: float | None = None
    proof_image_url: str | None = None


class VoteCreate(BaseModel):
    user_id: str = "demo-user"
    vote: int = Field(ge=-1, le=1)


class ObservationOut(BaseModel):
    id: int
    store_id: int
    price: Decimal
    is_promotion: bool
    promotion_label: str | None
    observed_at: datetime
    confirmation_score: float
    confidence: float
    distance_km: float | None = None
    store_name: str
    chain: str

    class Config:
        from_attributes = True
