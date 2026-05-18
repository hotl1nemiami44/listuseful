import os
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .database import SessionLocal
from . import crud
from .parsers import fetch_product
from .telegram_notify import send_price_alert
from dotenv import load_dotenv

load_dotenv()

scheduler = AsyncIOScheduler()

async def check_prices():
    db = SessionLocal()
    try:
        products = crud.get_products(db)
        for product in products:
            info = await fetch_product(product.marketplace, product.article)
            if not info:
                continue

            old_price = product.current_price
            new_price = info.price

            if old_price and new_price < old_price:
                change_pct = ((old_price - new_price) / old_price) * 100
                if change_pct >= product.alert_threshold:
                    await send_price_alert(
                        product_name=product.name or product.article,
                        marketplace=product.marketplace,
                        old_price=old_price,
                        new_price=new_price,
                        product_url=product.product_url or "",
                    )

            crud.update_product_price(db, product, new_price)
    finally:
        db.close()

def start_scheduler():
    interval = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))
    scheduler.add_job(check_prices, "interval", minutes=interval, id="price_check")
    scheduler.start()
