import re
from decimal import Decimal

from selectolax.parser import HTMLParser

from app.parsers.base import BaseParser, ParserError, to_decimal_price
from app.schemas import ParsedProduct


# Пороги диапазонов корзин WB (vol = nm // 100_000).
# Если nm выше последнего порога — используется последняя корзина.
# Актуально на 2025: корзины доросли до basket-40+.
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
    (5813, "29"),
    (6125, "30"),
    (6437, "31"),
    (6749, "32"),
    (7061, "33"),
    (7665, "34"),
    (8669, "35"),
    (10889, "36"),
    (13243, "37"),
    (15990, "38"),
    (17990, "39"),
    (100000, "40"),
]


class WildberriesParser(BaseParser):
    marketplace = "wb"

    # Канонический эндпоинт WB. v2/detail — основной рабочий путь;
    # v2/list — синоним для нескольких nm (работает и для одного).
    CARD_ENDPOINTS = (
        "https://card.wb.ru/cards/v2/detail",
        "https://card.wb.ru/cards/v2/list",
    )

    # URL карточки товара для браузерного фолбэка
    PRODUCT_PAGE = "https://www.wildberries.ru/catalog/{sku}/detail.aspx"

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

        # API первичен — быстрее и легче. При 404 (а пути регулярно ротируются)
        # сразу идём в браузер через crawl4ai/Playwright.
        product, api_error = await self._fetch_from_api(sku)
        if product is not None:
            price = self._extract_price(product)
            if price is not None:
                return ParsedProduct(
                    title=self._build_title(product, sku),
                    price=price,
                    image_url=self._image_url(sku),
                )
            api_error = ParserError("WB: цена не найдена в ответе API")

        try:
            return await self._parse_via_browser(sku)
        except ParserError as browser_err:
            raise ParserError(
                f"WB: API не сработал ({api_error}); браузер тоже: {browser_err}"
            ) from browser_err

    async def _fetch_from_api(self, sku: str) -> tuple[dict | None, Exception | None]:
        params = {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",  # Москва (без региона WB иногда отдаёт 400)
            "spp": "30",
            "nm": sku,
        }
        last_error: Exception | None = None
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
                return products[0], None
            last_error = ParserError(f"WB: товар {sku} не найден ({endpoint})")
        return None, last_error or ParserError("WB: все эндпоинты вернули ошибку")

    async def _parse_via_browser(self, sku: str) -> ParsedProduct:
        from app.parsers.base import find_jsonld_product
        page_url = self.PRODUCT_PAGE.format(sku=sku)
        # Не блокируемся на конкретном CSS — WB периодически меняет классы.
        # Просто берём отрендеренный HTML и парсим из всех возможных источников.
        resp = await self._get_browser(page_url, wait_selector=None)
        html = resp.text
        tree = HTMLParser(html)

        # 1. JSON-LD (есть у любого SEO-чувствительного товара)
        jsonld = find_jsonld_product(html)
        if jsonld:
            offers = jsonld.get("offers")
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                price = to_decimal_price(offers.get("price") or offers.get("lowPrice"))
                if price is not None and price > 0:
                    title = (jsonld.get("name") or f"Товар WB {sku}").strip()
                    return ParsedProduct(
                        title=title, price=price, image_url=self._image_url(sku)
                    )

        # 2. Classes-based селекторы (несколько поколений вёрстки WB)
        price = None
        for selector in (
            "ins.price-block__final-price",
            ".price-block__final-price",
            ".price-block__wallet-price",
            '[class*="price-block__final-price"]',
            '[class*="priceBlockFinalPrice"]',
            'span[class*="finalPrice"]',
            'span[data-link*="priceProduct"]',
        ):
            node = tree.css_first(selector)
            if node:
                price = to_decimal_price(node.text())
                if price is not None and price > 0:
                    break

        # 3. OG-метатеги
        if price is None:
            og_price = tree.css_first('meta[property="product:price:amount"]') \
                or tree.css_first('meta[property="og:price:amount"]')
            if og_price:
                price = to_decimal_price(og_price.attributes.get("content"))

        # 4. Регэксп по сырому HTML — последний шанс ("1 299 ₽")
        if price is None:
            m = re.search(r'(\d[\d\s\xa0]{0,7})\s*(?:&nbsp;)?₽', html)
            if m:
                price = to_decimal_price(m.group(1))

        if price is None or price <= 0:
            raise ParserError("WB: цена не найдена на странице товара (вёрстка изменилась)")

        title_node = (
            tree.css_first("h1.product-page__title")
            or tree.css_first('h1[data-link*="productName"]')
            or tree.css_first("h1")
        )
        title = title_node.text(strip=True) if title_node else f"Товар WB {sku}"

        return ParsedProduct(
            title=title,
            price=price,
            image_url=self._image_url(sku),
        )

    @staticmethod
    def _build_title(product: dict, sku: str) -> str:
        title = (product.get("name") or "").strip() or f"Товар WB {sku}"
        brand = (product.get("brand") or "").strip()
        if brand and brand.lower() not in title.lower():
            title = f"{brand} {title}"
        return title

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
