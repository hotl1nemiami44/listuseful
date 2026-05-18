import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Product, PriceHistory
from app.parsers.factory import get_parser
from app.parsers.base import ParserError
from app.notifier import send_price_drop

logger = logging.getLogger(__name__)


async def check_single_product(db: Session, product: Product) -> None:
    try:
        parser = get_parser(product.url)
        result = await parser.parse(product.url)
    except ParserError as e:
        logger.warning("Не удалось проверить товар %s: %s", product.id, e)
        return

    old_price = Decimal(product.current_price)
    new_price = Decimal(result.price)

    db.add(PriceHistory(product_id=product.id, price=new_price))

    if new_price < old_price and old_price > 0:
        drop_percent = float((old_price - new_price) / old_price * 100)
        if drop_percent >= product.threshold_percent:
            await send_price_drop(
                chat_id=product.user.telegram_chat_id,
                title=product.title,
                url=product.url,
                old_price=old_price,
                new_price=new_price,
                image_url=product.image_url,
            )
            logger.info("Уведомление отправлено: товар %s, −%.1f%%", product.id, drop_percent)

    product.current_price = new_price
    db.commit()


async def check_all_products() -> None:
    logger.info("Запуск плановой проверки цен")
    db = SessionLocal()
    try:
        products = db.query(Product).filter(Product.is_active == True).all()  # noqa: E712
        for product in products:
            await check_single_product(db, product)
    finally:
        db.close()
    logger.info("Проверка завершена")