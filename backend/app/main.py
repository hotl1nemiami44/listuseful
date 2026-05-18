from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os

from .database import engine, get_db, Base
from . import models, schemas, crud
from .parsers import fetch_product
from .scheduler import start_scheduler, check_prices

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Price Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    start_scheduler()

@app.get("/api/products", response_model=List[schemas.ProductResponse])
def list_products(db: Session = Depends(get_db)):
    products = crud.get_products(db)
    result = []
    for p in products:
        history = crud.get_price_history(db, p.id)
        pd = schemas.ProductResponse(
            id=p.id,
            article=p.article,
            marketplace=p.marketplace,
            name=p.name,
            image_url=p.image_url,
            product_url=p.product_url,
            current_price=p.current_price,
            alert_threshold=p.alert_threshold,
            created_at=p.created_at,
            updated_at=p.updated_at,
            price_history=[
                schemas.PriceHistoryItem(price=h.price, recorded_at=h.recorded_at)
                for h in history
            ],
        )
        result.append(pd)
    return result

@app.post("/api/products", response_model=schemas.ProductResponse)
async def add_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    info = await fetch_product(product.marketplace, product.article)
    if not info:
        raise HTTPException(status_code=422, detail=f"Не удалось получить данные с {product.marketplace} по артикулу {product.article}")
    db_product = crud.create_product(db, product, info)
    history = crud.get_price_history(db, db_product.id)
    return schemas.ProductResponse(
        id=db_product.id,
        article=db_product.article,
        marketplace=db_product.marketplace,
        name=db_product.name,
        image_url=db_product.image_url,
        product_url=db_product.product_url,
        current_price=db_product.current_price,
        alert_threshold=db_product.alert_threshold,
        created_at=db_product.created_at,
        updated_at=db_product.updated_at,
        price_history=[
            schemas.PriceHistoryItem(price=h.price, recorded_at=h.recorded_at)
            for h in history
        ],
    )

@app.delete("/api/products/{product_id}")
def remove_product(product_id: int, db: Session = Depends(get_db)):
    product = crud.delete_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return {"ok": True}

@app.patch("/api/products/{product_id}", response_model=schemas.ProductResponse)
def update_product(product_id: int, data: schemas.ProductUpdate, db: Session = Depends(get_db)):
    product = None
    if data.alert_threshold is not None:
        product = crud.update_product_threshold(db, product_id, data.alert_threshold)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    history = crud.get_price_history(db, product.id)
    return schemas.ProductResponse(
        id=product.id,
        article=product.article,
        marketplace=product.marketplace,
        name=product.name,
        image_url=product.image_url,
        product_url=product.product_url,
        current_price=product.current_price,
        alert_threshold=product.alert_threshold,
        created_at=product.created_at,
        updated_at=product.updated_at,
        price_history=[
            schemas.PriceHistoryItem(price=h.price, recorded_at=h.recorded_at)
            for h in history
        ],
    )

@app.post("/api/refresh")
async def manual_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(check_prices)
    return {"ok": True, "message": "Обновление запущено"}

# Serve frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(frontend_path, "index.html"))
