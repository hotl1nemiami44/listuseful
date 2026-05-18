import httpx
from typing import Optional
from .base import BaseParser, ProductInfo
from bs4 import BeautifulSoup
import json, re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

class AliexpressParser(BaseParser):
    async def fetch(self, article: str) -> Optional[ProductInfo]:
        try:
            url = f"https://www.aliexpress.com/item/{article.strip()}.html"
            async with httpx.AsyncClient(
                timeout=25,
                headers=HEADERS,
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
                r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")

            # AliExpress embeds product data in window.runParams
            for script in soup.find_all("script"):
                text = script.string or ""
                if "window.runParams" in text:
                    m = re.search(r"data:\s*(\{.+?\})\s*};", text, re.DOTALL)
                    if m:
                        try:
                            obj = json.loads(m.group(1))
                            ae_data = obj.get("actionModule", {})
                            title_data = obj.get("titleModule", {})
                            image_data = obj.get("imageModule", {})
                            price = float(ae_data.get("price", {}).get("formatedAmount", "0").replace(",", ".").replace("$", "").strip() or 0)
                            if price:
                                images = image_data.get("imagePathList", [])
                                return ProductInfo(
                                    name=title_data.get("subject", f"AliExpress #{article}"),
                                    price=price,
                                    image_url=images[0] if images else None,
                                    product_url=url,
                                    currency="USD",
                                )
                        except Exception:
                            pass

            # fallback: JSON-LD
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    obj = json.loads(script.string)
                    if obj.get("@type") == "Product":
                        offers = obj.get("offers", {})
                        price = float(offers.get("price", 0))
                        if price:
                            return ProductInfo(
                                name=obj.get("name", f"AliExpress #{article}"),
                                price=price,
                                image_url=obj.get("image"),
                                product_url=url,
                                currency=offers.get("priceCurrency", "USD"),
                            )
                except Exception:
                    continue

            return None
        except Exception:
            return None
