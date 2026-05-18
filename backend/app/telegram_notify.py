import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

async def send_price_alert(product_name: str, marketplace: str, old_price: float, new_price: float, product_url: str):
    if not BOT_TOKEN or not CHAT_ID:
        return

    change_pct = ((old_price - new_price) / old_price) * 100
    text = (
        f"🔥 Снижение цены!\n\n"
        f"📦 {product_name}\n"
        f"🏪 {marketplace.capitalize()}\n\n"
        f"Было: {old_price:.2f} ₽\n"
        f"Стало: {new_price:.2f} ₽\n"
        f"Скидка: -{change_pct:.1f}%\n\n"
        f"🔗 {product_url}"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
        except Exception:
            pass
