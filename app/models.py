from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, Integer, ForeignKey, Numeric, Boolean, DateTime, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    products: Mapped[list["Product"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    marketplace: Mapped[str] = mapped_column(String(32))  # ozon | wb | ym | ali
    title: Mapped[str] = mapped_column(String(500))
    image_url: Mapped[str] = mapped_column(String(1000), default="")
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    threshold_percent: Mapped[float] = mapped_column(Float, default=5.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="products")
    history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="PriceHistory.checked_at"
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    product: Mapped["Product"] = relationship(back_populates="history")


Index("ix_price_history_product_checked", PriceHistory.product_id, PriceHistory.checked_at)