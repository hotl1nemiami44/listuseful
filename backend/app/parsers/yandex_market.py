import httpx
from typing import Optional
from .base import BaseParser, ProductInfo
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

class YandexMarketParser(BaseParser):
    async def fetch(self, article: str) -> Optional[ProductInfo]:
        try:
            search_url = f"https://market.yandex.ru/search?text={article.strip()}"
            async with httpx.AsyncClient(
                timeout=20,
                headers=HEADERS,
                follow_redirects=True,
            ) as client:
                r = await client.get(search_url)
                r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")

            # try to find JSON-LD data
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    import json
                    obj = json.loads(script.string)
                    items = obj if isinstance(obj, list) else [obj]
                    for item in items:
                        if item.get("@type") in ("Product", "ItemPage"):
                            price_info = item.get("offers", {})
                            price = float(price_info.get("price", 0))
                            if price:
                                return ProductInfo(
                                    name=item.get("name", f"YM #{article}"),
                                    price=price,
                                    image_url=item.get("image"),
                                    product_url=search_url,
                                )
                except Exception:
                    continue
            return None
        except Exception:
            return None
