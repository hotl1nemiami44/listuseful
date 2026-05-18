from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime
from .database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    article = Column(String, nullable=False)
    marketplace = Column(String, nullable=False)
    name = Column(String)
    image_url = Column(String)
    product_url = Column(String)
    current_price = Column(Float)
    alert_threshold = Column(Float, default=5.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)
