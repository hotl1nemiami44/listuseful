import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, init_db
from app.models import User, Product, PriceHistory
from app.schemas import ProductCreate, ProductUpdate, ProductOut, ProductDetail
from app.parsers.factory import get_parser
from app.parsers.base import ParserError
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.tasks.check_prices import check_single_product

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Price Tracker", lifespan=lifespan)

_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend):
    app.mount("/static", StaticFiles(directory=_frontend), name="static")


def get_or_create_user(db: Session, chat_id: str) -> User:
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if not user:
        user = User(telegram_chat_id=chat_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def current_user(
    x_chat_id: str = Header(..., description="Telegram chat ID пользователя"),
    db: Session = Depends(get_db),
) -> User:
    return get_or_create_user(db, x_chat_id)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    index = os.path.join(_frontend, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return {"message": "Price Tracker API"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.post("/products", response_model=ProductOut, status_code=201)
async def add_product(
    payload: ProductCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    url = str(payload.url)
    try:
        parser = get_parser(url)
        result = await parser.parse(url)
    except ParserError as e:
        raise HTTPException(status_code=400, detail=str(e))

    product = Product(
        user_id=user.id,
        url=url,
        marketplace=parser.marketplace,
        title=result.title,
        image_url=result.image_url,
        current_price=result.price,
        threshold_percent=payload.threshold_percent or settings.default_threshold_percent,
    )
    db.add(product)
    db.flush()
    db.add(PriceHistory(product_id=product.id, price=result.price))
    db.commit()
    db.refresh(product)
    return product


@app.get("/products", response_model=list[ProductOut])
def list_products(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.user_id == user.id).all()


@app.get("/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product


@app.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    if payload.threshold_percent is not None:
        product.threshold_percent = payload.threshold_percent
    if payload.is_active is not None:
        product.is_active = payload.is_active
    db.commit()
    db.refresh(product)
    return product


@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    db.delete(product)
    db.commit()


@app.post("/products/{product_id}/check", response_model=ProductOut)
async def check_now(product_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Принудительная проверка цены прямо сейчас."""
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    await check_single_product(db, product)
    db.refresh(product)
    return product