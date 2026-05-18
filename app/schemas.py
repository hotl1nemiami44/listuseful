from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, HttpUrl, Field


class ProductCreate(BaseModel):
    url: HttpUrl
    threshold_percent: Optional[float] = Field(default=None, ge=0.1, le=100)


class ProductUpdate(BaseModel):
    threshold_percent: Optional[float] = Field(default=None, ge=0.1, le=100)
    is_active: Optional[bool] = None


class PriceHistoryOut(BaseModel):
    price: Decimal
    checked_at: datetime

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    url: str
    marketplace: str
    title: str
    image_url: str
    current_price: Decimal
    threshold_percent: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductDetail(ProductOut):
    history: list[PriceHistoryOut]


class ParsedProduct(BaseModel):
    """Результат работы парсера."""
    title: str
    price: Decimal
    image_url: str = ""