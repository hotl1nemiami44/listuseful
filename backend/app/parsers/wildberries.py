import httpx
from typing import Optional
from .base import BaseParser, ProductInfo

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

def _basket_url(article_id: int) -> str:
    vol = article_id // 100000
    part = article_id // 1000
    breakpoints = [
        (143, "01"), (287, "02"), (431, "03"), (719, "04"),
        (1007, "05"), (1061, "06"), (1115, "07"), (1169, "08"),
        (1313, "09"), (1601, "10"), (1655, "11"), (1919, "12"),
        (2045, "13"), (2189, "14"), (2405, "15"), (2621, "16"),
        (2837, "17"),
    ]
    basket = "18"
    for max_vol, num in breakpoints:
        if vol <= max_vol:
            basket = num
            break
    return f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{article_id}/images/big/1.jpg"

class WildberriesParser(BaseParser):
    async def fetch(self, article: str) -> Optional[ProductInfo]:
        try:
            article_id = int(article.strip())
            url = (
                f"https://card.wb.ru/cards/v1/detail"
                f"?appType=1&curr=rub&dest=-1257786&spp=30&nm={article_id}"
            )
            async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()

            products = data.get("data", {}).get("products", [])
            if not products:
                return None

            p = products[0]
            price = p.get("salePriceU", p.get("priceU", 0)) / 100

            return ProductInfo(
                name=p.get("name", ""),
                price=price,
                image_url=_basket_url(article_id),
                product_url=f"https://www.wildberries.ru/catalog/{article_id}/detail.aspx",
            )
        except Exception:
            return None
