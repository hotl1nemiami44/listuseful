from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class ProductCreate(BaseModel):
    article: str
    marketplace: str  # wildberries | ozon | yandex_market | aliexpress
    alert_threshold: float = 5.0

class ProductUpdate(BaseModel):
    alert_threshold: Optional[float] = None

class PriceHistoryItem(BaseModel):
    price: float
    recorded_at: datetime

    class Config:
        from_attributes = True

class ProductResponse(BaseModel):
    id: int
    article: str
    marketplace: str
    name: Optional[str]
    image_url: Optional[str]
    product_url: Optional[str]
    current_price: Optional[float]
    alert_threshold: float
    created_at: datetime
    updated_at: datetime
    price_history: List[PriceHistoryItem] = []

    class Config:
        from_attributes = True
