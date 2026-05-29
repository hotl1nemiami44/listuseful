import json as _json
import re
from decimal import Decimal
from urllib.parse import urlparse, urlunparse

from app.parsers.base import BaseParser, ParserError, find_jsonld_product, to_decimal_price
from app.schemas import ParsedProduct


class OzonParser(BaseParser):
    marketplace = "ozon"
    ENTRYPOINT = "https://api.ozon.ru/entrypoint-api.bx/page/json/v2"

    api_headers = {
        "Accept": "application/json",
        "Origin": "https://www.ozon.ru",
        "Referer": "https://www.ozon.ru/",
        "x-o3-app-name": "dweb_client",
        "x-o3-app-version": "release_8-7-2024",
        "x-o3-device-type": "desktop",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "ozon.ru" in url

    async def parse(self, url: str) -> ParsedProduct:
        # Сначала пробуем мобильный/SPA endpoint — он отдаёт JSON c виджетами.
        try:
            result = await self._parse_via_api(url)
            if result is not None:
                return result
        except ParserError as e:
            api_err = str(e)
        else:
            api_err = "виджеты не содержат цену"

        # Fallback: HTML карточки → JSON-LD (когда доступен).
        try:
            html_resp = await self._get(url)
            jsonld = find_jsonld_product(html_resp.text)
        except ParserError as e:
            raise ParserError(f"Ozon: {api_err}; HTML недоступен: {e}") from e

        if jsonld:
            result = self._from_jsonld(jsonld)
            if result is not None:
                return result

        # Финальный фолбэк — Playwright (если установлен)
        try:
            browser_resp = await self._get_browser(
                url,
                wait_selector='script[type="application/ld+json"], [data-widget="webPrice"]',
            )
        except ParserError as pw_err:
            raise ParserError(
                f"Ozon: {api_err}. HTML тоже без данных. "
                f"Playwright недоступен: {pw_err}"
            ) from pw_err

        jsonld = find_jsonld_product(browser_resp.text)
        if jsonld:
            result = self._from_jsonld(jsonld)
            if result is not None:
                return result

        raise ParserError(f"Ozon: даже Playwright не нашёл данных товара")

    async def _parse_via_api(self, url: str) -> ParsedProduct | None:
        path = urlparse(url).path  # /product/xxx-123456789/
        if not path:
            raise ParserError("Ozon: пустой path в URL")
        try:
            resp = await self._get(
                self.ENTRYPOINT,
                params={"url": path},
                headers=self.api_headers,
            )
            data = resp.json()
        except ParserError:
            raise
        except Exception as e:
            raise ParserError(f"Ozon: ошибка запроса API: {e}") from e

        widget_states = data.get("widgetStates") or {}
        if not widget_states:
            raise ParserError("Ozon: widgetStates пуст (вероятно нужен прокси/JS)")

        title = None
        price: Decimal | None = None
        image_url = ""

        for key, raw in widget_states.items():
            if not isinstance(raw, str):
                continue
            try:
                parsed = _json.loads(raw)
            except _json.JSONDecodeError:
                continue

            if not title and key.startswith("webProductHeading"):
                title = parsed.get("title") or parsed.get("name")

            if price is None and key.startswith("webPrice"):
                price = self._price_from_widget(parsed)

            if not image_url and key.startswith(("webGallery", "webStickyProducts")):
                image_url = self._image_from_widget(parsed)

        if price is None:
            return None

        return ParsedProduct(
            title=(title or "Товар Ozon").strip(),
            price=price,
            image_url=image_url or "",
        )

    @staticmethod
    def _price_from_widget(parsed: dict) -> Decimal | None:
        # Перебираем известные поля в порядке "карточная" → обычная → оригинал
        for key in ("cardPrice", "price", "finalPrice", "originalPrice"):
            value = parsed.get(key)
            if isinstance(value, dict):
                # Иногда price хранится как { "price": "1 299 ₽" }
                value = value.get("price") or value.get("text") or value.get("value")
            p = to_decimal_price(value)
            if p is not None and p > 0:
                return p
        return None

    @staticmethod
    def _image_from_widget(parsed: dict) -> str:
        images = parsed.get("images") or parsed.get("coverImages") or []
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("src") or first.get("url") or ""
        cover = parsed.get("coverImage")
        if isinstance(cover, str):
            return cover
        if isinstance(cover, dict):
            return cover.get("src") or ""
        return ""

    @staticmethod
    def _from_jsonld(data: dict) -> ParsedProduct | None:
        offers = data.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if not isinstance(offers, dict):
            return None
        price = to_decimal_price(offers.get("price"))
        if price is None:
            return None
        image = data.get("image") or ""
        if isinstance(image, list):
            image = image[0] if image else ""
        return ParsedProduct(
            title=(data.get("name") or "Товар Ozon").strip(),
            price=price,
            image_url=image,
        )
