import re
from decimal import Decimal

from app.parsers.base import BaseParser, ParserError, to_decimal_price
from app.schemas import ParsedProduct


# Пороги diапазонов корзин WB (vol = nm // 100_000).
# Если nm выше последнего порога — используется последняя корзина.
_BASKET_BOUNDS = [
    (143, "01"),
    (287, "02"),
    (431, "03"),
    (719, "04"),
    (1007, "05"),
    (1061, "06"),
    (1115, "07"),
    (1169, "08"),
    (1313, "09"),
    (1601, "10"),
    (1655, "11"),
    (1919, "12"),
    (2045, "13"),
    (2189, "14"),
    (2405, "15"),
    (2621, "16"),
    (2837, "17"),
    (3053, "18"),
    (3269, "19"),
    (3485, "20"),
    (3701, "21"),
    (3917, "22"),
    (4133, "23"),
    (4349, "24"),
    (4565, "25"),
    (4877, "26"),
    (5189, "27"),
    (5501, "28"),
]


class WildberriesParser(BaseParser):
    marketplace = "wb"

    # WB периодически меняет путь — пробуем известные варианты по порядку.
    CARD_ENDPOINTS = (
        "https://card.wb.ru/cards/v2/list",
        "https://card.wb.ru/cards/v4/list",
        "https://card.wb.ru/cards/v1/detail",
        "https://card.wb.ru/cards/detail",
    )

    headers = {
        **BaseParser.headers,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.wildberries.ru",
        "Referer": "https://www.wildberries.ru/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "wildberries.ru" in url or "wb.ru" in url

    @staticmethod
    def _extract_sku(url: str) -> str:
        # Поддерживаем /catalog/12345/detail.aspx и /product?card=12345
        m = re.search(r"/catalog/(\d+)", url) or re.search(r"[?&](?:nm|card)=(\d+)", url)
        if not m:
            raise ParserError("WB: не удалось извлечь артикул из URL")
        return m.group(1)

    @staticmethod
    def _basket(sku: str) -> str:
        vol = int(sku) // 100_000
        for upper, basket in _BASKET_BOUNDS:
            if vol <= upper:
                return basket
        return _BASKET_BOUNDS[-1][1]

    @classmethod
    def _image_url(cls, sku: str) -> str:
        sku_int = int(sku)
        vol = sku_int // 100_000
        part = sku_int // 1000
        basket = cls._basket(sku)
        return f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/big/1.webp"

    async def parse(self, url: str) -> ParsedProduct:
        sku = self._extract_sku(url)
        params = {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",  # Москва (без региона WB иногда отдаёт 400)
            "nm": sku,
        }

        last_error: Exception | None = None
        product: dict | None = None
        for endpoint in self.CARD_ENDPOINTS:
            try:
                resp = await self._get(endpoint, params=params)
                data = resp.json()
            except ParserError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = ParserError(f"WB: ошибка запроса {endpoint}: {e}")
                continue

            products = (data.get("data") or {}).get("products") or []
            if products:
                product = products[0]
                break
            last_error = ParserError(f"WB: товар {sku} не найден ({endpoint})")

        if product is None:
            raise last_error or ParserError("WB: все эндпоинты вернули ошибку")

        price = self._extract_price(product)
        if price is None:
            raise ParserError("WB: цена не найдена в ответе API")

        title = (product.get("name") or "").strip() or f"Товар WB {sku}"
        # Бренд + название читабельнее
        brand = (product.get("brand") or "").strip()
        if brand and brand.lower() not in title.lower():
            title = f"{brand} {title}"

        return ParsedProduct(
            title=title,
            price=price,
            image_url=self._image_url(sku),
        )

    @staticmethod
    def _extract_price(product: dict) -> Decimal | None:
        # Новая схема (v2): sizes[].price.product / total (в копейках)
        for size in product.get("sizes") or []:
            price_block = size.get("price")
            if isinstance(price_block, dict):
                kopecks = (
                    price_block.get("product")
                    or price_block.get("total")
                    or price_block.get("basic")
                )
                if kopecks:
                    return Decimal(kopecks) / 100

        # Старая схема: salePriceU / priceU (тоже в копейках)
        for key in ("salePriceU", "priceU", "extendedPriceU"):
            if product.get(key):
                return Decimal(product[key]) / 100

        # Самый старый формат — строка "1 299 ₽"
        for key in ("salePrice", "price"):
            if product.get(key):
                p = to_decimal_price(product[key])
                if p:
                    return p
        return None
