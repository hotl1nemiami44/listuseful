import httpx
from typing import Optional
from .base import BaseParser, ProductInfo
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "x-o3-app-name": "ozon.ru",
    "x-o3-app-version": "3.0",
    "Referer": "https://www.ozon.ru/",
}

class OzonParser(BaseParser):
    async def fetch(self, article: str) -> Optional[ProductInfo]:
        try:
            url = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{article.strip()}/"
            async with httpx.AsyncClient(
                timeout=20,
                headers=HEADERS,
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()

            # walk widget tree to find product info
            widgets = data.get("widgetStates", {})
            name = None
            price = None
            image_url = None

            for key, value in widgets.items():
                if isinstance(value, str):
                    try:
                        obj = json.loads(value)
                    except Exception:
                        continue
                    if "title" in obj and name is None:
                        name = obj.get("title")
                    if "price" in obj and price is None:
                        raw = str(obj.get("price", "")).replace(" ", "").replace(" ", "").replace("₽", "").replace(",", ".")
                        try:
                            price = float(raw)
                        except Exception:
                            pass
                    if "coverImage" in obj and image_url is None:
                        image_url = obj.get("coverImage")

            if not price:
                return None

            return ProductInfo(
                name=name or f"Ozon #{article}",
                price=price,
                image_url=image_url,
                product_url=f"https://www.ozon.ru/product/{article.strip()}/",
            )
        except Exception:
            return None
