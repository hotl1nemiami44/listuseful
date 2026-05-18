import re
from decimal import Decimal

from app.parsers.base import BaseParser, ParserError
from app.schemas import ParsedProduct


class WildberriesParser(BaseParser):
    marketplace = "wb"
    CARD_API = "https://card.wb.ru/cards/v2/detail"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "wildberries.ru" in url

    @staticmethod
    def _extract_sku(url: str) -> str:
        m = re.search(r"/catalog/(\d+)/", url)
        if not m:
            raise ParserError("Не удалось извлечь артикул из URL Wildberries")
        return m.group(1)

    @staticmethod
    def _image_url(sku: str) -> str:
        # WB раскладывает картинки по "корзинам" в зависимости от диапазона артикула
        sku_int = int(sku)
        vol = sku_int // 100_000
        part = sku_int // 1000

        if vol <= 143:    basket = "01"
        elif vol <= 287:  basket = "02"
        elif vol <= 431:  basket = "03"
        elif vol <= 719:  basket = "04"
        elif vol <= 1007: basket = "05"
        elif vol <= 1061: basket = "06"
        elif vol <= 1115: basket = "07"
        elif vol <= 1169: basket = "08"
        elif vol <= 1313: basket = "09"
        elif vol <= 1601: basket = "10"
        elif vol <= 1655: basket = "11"
        elif vol <= 1919: basket = "12"
        elif vol <= 2045: basket = "13"
        elif vol <= 2189: basket = "14"
        elif vol <= 2405: basket = "15"
        elif vol <= 2621: basket = "16"
        else:             basket = "17"

        return f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/big/1.webp"

    async def parse(self, url: str) -> ParsedProduct:
        sku = self._extract_sku(url)
        params = {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",  # Москва
            "spp": "30",
            "nm": sku,
        }
        try:
            resp = await self._get(self.CARD_API, params=params)
            data = resp.json()
            product = data["data"]["products"][0]
        except (KeyError, IndexError, ValueError) as e:
            raise ParserError(f"WB: некорректный ответ API: {e}") from e

        # Цена приходит в копейках в новой схеме (sizes[].price.product) или ×100 в product.salePriceU
        price_kopecks = None
        for size in product.get("sizes", []):
            if "price" in size and size["price"]:
                price_kopecks = size["price"].get("product") or size["price"].get("total")
                if price_kopecks:
                    break
        if price_kopecks is None:
            price_kopecks = product.get("salePriceU") or product.get("priceU")
        if price_kopecks is None:
            raise ParserError("WB: цена не найдена")

        return ParsedProduct(
            title=product.get("name", "").strip() or f"Товар WB {sku}",
            price=Decimal(price_kopecks) / 100,
            image_url=self._image_url(sku),
        )