import json
import re
from decimal import Decimal
from typing import Any, Optional

from app.parsers.base import (
    BaseParser,
    ParserError,
    extract_balanced_json,
    find_jsonld_product,
    to_decimal_price,
)
from app.schemas import ParsedProduct


class AliexpressParser(BaseParser):
    marketplace = "ali"

    headers = {
        **BaseParser.headers,
        # На .ru без RU-локали часто редиректит на .com с другим SSR
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "aliexpress." in url  # .com / .ru

    async def parse(self, url: str) -> ParsedProduct:
        try:
            resp = await self._get(url)
        except ParserError:
            raise
        except Exception as e:
            raise ParserError(f"Ali: ошибка запроса: {e}") from e

        html = resp.text

        # 1. JSON-LD — самый стабильный путь
        jsonld = find_jsonld_product(html)
        if jsonld:
            result = self._from_jsonld(jsonld)
            if result is not None:
                return result

        # 2. window.runParams = {...} (актуально на старом aliexpress.com)
        run_params = _extract_inline_json(html, r"window\.runParams\s*=\s*")
        if run_params is not None:
            payload = run_params.get("data") if isinstance(run_params, dict) else None
            if isinstance(payload, dict):
                result = self._from_run_params(payload)
                if result is not None:
                    return result

        # 3. _d_c_.DCData = {...} (актуально на aliexpress.ru)
        dc_data = _extract_inline_json(html, r"_d_c_\.DCData\s*=\s*")
        if isinstance(dc_data, dict):
            result = self._from_dc_data(dc_data)
            if result is not None:
                return result

        # 4. <script id="__INITIAL_STATE__">{...}</script>
        m = re.search(
            r'<script[^>]+id=["\']__INITIAL_STATE__["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if m:
            try:
                initial_state = json.loads(m.group(1))
            except json.JSONDecodeError:
                initial_state = None
            if isinstance(initial_state, dict):
                result = self._from_dc_data(initial_state) or self._from_run_params(initial_state)
                if result is not None:
                    return result

        raise ParserError(
            "Ali: не удалось найти данные товара в HTML (вероятно требуется "
            "JS-рендеринг или регион/куки)"
        )

    @staticmethod
    def _from_jsonld(data: dict) -> Optional[ParsedProduct]:
        offers = data.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if not isinstance(offers, dict):
            return None
        price = to_decimal_price(offers.get("price") or offers.get("lowPrice"))
        if price is None:
            return None
        image = data.get("image") or ""
        if isinstance(image, list):
            image = image[0] if image else ""
        return ParsedProduct(
            title=(data.get("name") or "Товар AliExpress").strip(),
            price=price,
            image_url=image or "",
        )

    @staticmethod
    def _from_run_params(payload: dict) -> Optional[ParsedProduct]:
        title = (
            _get_path(payload, "titleModule", "subject")
            or _get_path(payload, "productInfoComponent", "subject")
            or _get_path(payload, "pageModule", "title")
            or "Товар AliExpress"
        )

        price = None
        # Старый формат (.com)
        for path in (
            ("priceModule", "minActivityAmount", "value"),
            ("priceModule", "minAmount", "value"),
            ("priceModule", "maxActivityAmount", "value"),
            ("priceComponent", "discountPrice", "minPrice"),
            ("priceComponent", "discountPrice", "minActivityAmount", "value"),
            ("priceComponent", "salePrice", "minPrice"),
        ):
            v = _get_path(payload, *path)
            price = to_decimal_price(v)
            if price is not None:
                break

        if price is None:
            # Иногда форматированная строка вида "1 299,00 ₽"
            for path in (
                ("priceModule", "formatedActivityPrice"),
                ("priceModule", "formatedPrice"),
                ("priceComponent", "discountPriceText"),
            ):
                v = _get_path(payload, *path)
                price = to_decimal_price(v)
                if price is not None:
                    break

        if price is None:
            return None

        image = ""
        images = _get_path(payload, "imageModule", "imagePathList") or []
        if isinstance(images, list) and images:
            image = images[0]

        return ParsedProduct(title=str(title).strip(), price=price, image_url=image)

    @staticmethod
    def _from_dc_data(data: dict) -> Optional[ParsedProduct]:
        # На aliexpress.ru структура отличается, но обычно есть productData/SKU
        product = (
            _get_path(data, "productData")
            or _get_path(data, "data", "productData")
            or _get_path(data, "props", "pageProps", "productData")
            or data
        )
        if not isinstance(product, dict):
            return None

        title = (
            product.get("title")
            or product.get("subject")
            or _get_path(product, "productInfo", "title")
            or "Товар AliExpress"
        )

        price = None
        for path in (
            ("sku", "def", "promotionPrice", "minPrice"),
            ("sku", "def", "salePrice", "minPrice"),
            ("price", "salePrice", "minPrice"),
            ("price", "promotionPrice", "minPrice"),
            ("priceInfo", "salePrice"),
            ("priceInfo", "price"),
        ):
            v = _get_path(product, *path)
            price = to_decimal_price(v)
            if price is not None:
                break

        if price is None:
            return None

        image = ""
        images = (
            _get_path(product, "imageList")
            or _get_path(product, "images")
            or _get_path(product, "productInfo", "images")
            or []
        )
        if isinstance(images, list) and images:
            first = images[0]
            image = first if isinstance(first, str) else (first.get("url") or first.get("src") or "")

        return ParsedProduct(title=str(title).strip(), price=price, image_url=image or "")


def _extract_inline_json(html: str, prefix_pattern: str) -> Any:
    """Находит `<prefix>{...};` и возвращает распарсенный JSON или None."""
    m = re.search(prefix_pattern, html)
    if not m:
        return None
    start = m.end()
    # Пропускаем пробелы до первой '{' или '['
    while start < len(html) and html[start] in " \t\r\n":
        start += 1
    if start >= len(html) or html[start] not in "{[":
        return None
    raw = extract_balanced_json(html, start)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _get_path(data: Any, *keys: str) -> Any:
    cur = data
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
        if cur is None:
            return None
    return cur
