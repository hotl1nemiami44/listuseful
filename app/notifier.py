import logging
from decimal import Decimal

from telegram import Bot
from telegram.error import TelegramError

from app.config import settings

logger = logging.getLogger(__name__)

_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


async def send_price_drop(
    chat_id: str,
    title: str,
    url: str,
    old_price: Decimal,
    new_price: Decimal,
    image_url: str = "",
) -> None:
    diff = old_price - new_price
    percent = (diff / old_price * 100) if old_price > 0 else Decimal(0)
    text = (
        f"📉 <b>Цена снизилась!</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"Было: <s>{old_price} ₽</s>\n"
        f"Стало: <b>{new_price} ₽</b>\n"
        f"Скидка: −{diff} ₽ ({percent:.1f}%)\n\n"
        f'<a href="{url}">Открыть товар</a>'
    )
    try:
        bot = get_bot()
        if image_url:
            await bot.send_photo(chat_id=chat_id, photo=image_url, caption=text, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=False)
    except TelegramError as e:
        logger.error("Telegram error for chat %s: %s", chat_id, e)


async def send_text(chat_id: str, text: str) -> None:
    try:
        await get_bot().send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except TelegramError as e:
        logger.error("Telegram error for chat %s: %s", chat_id, e)