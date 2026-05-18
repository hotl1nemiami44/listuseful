from sqlalchemy.orm import Session
from . import models, schemas
from datetime import datetime

def get_products(db: Session):
    return db.query(models.Product).all()

def get_product(db: Session, product_id: int):
    return db.query(models.Product).filter(models.Product.id == product_id).first()

def create_product(db: Session, product: schemas.ProductCreate, info):
    db_product = models.Product(
        article=product.article,
        marketplace=product.marketplace,
        alert_threshold=product.alert_threshold,
        name=info.name if info else None,
        image_url=info.image_url if info else None,
        product_url=info.product_url if info else None,
        current_price=info.price if info else None,
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    if info:
        record = models.PriceHistory(product_id=db_product.id, price=info.price)
        db.add(record)
        db.commit()

    return db_product

def delete_product(db: Session, product_id: int):
    product = get_product(db, product_id)
    if product:
        db.query(models.PriceHistory).filter(models.PriceHistory.product_id == product_id).delete()
        db.delete(product)
        db.commit()
    return product

def get_price_history(db: Session, product_id: int):
    return (
        db.query(models.PriceHistory)
        .filter(models.PriceHistory.product_id == product_id)
        .order_by(models.PriceHistory.recorded_at)
        .all()
    )

def update_product_price(db: Session, product: models.Product, new_price: float):
    product.current_price = new_price
    product.updated_at = datetime.utcnow()
    db.add(product)
    record = models.PriceHistory(product_id=product.id, price=new_price)
    db.add(record)
    db.commit()

def update_product_threshold(db: Session, product_id: int, threshold: float):
    product = get_product(db, product_id)
    if product:
        product.alert_threshold = threshold
        db.commit()
        db.refresh(product)
    return product
