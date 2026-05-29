import json
import re
from decimal import Decimal
from typing import Optional

from selectolax.parser import HTMLParser

from app.parsers.base import BaseParser, ParserError, find_jsonld_product, to_decimal_price
from app.schemas import ParsedProduct


class YandexMarketParser(BaseParser):
    marketplace = "ym"

    headers = {
        **BaseParser.headers,
        # Маркет смотрит на эти хедеры — без них почти всегда antibot
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://market.yandex.ru/",
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "market.yandex.ru" in url

    async def parse(self, url: str) -> ParsedProduct:
        html, source = await self._fetch_html(url)
        result = self._try_extract(html)
        if result is not None:
            return result

        # curl_cffi/httpx упёрся в капчу — пробуем Playwright (если установлен)
        if source != "browser":
            try:
                resp = await self._get_browser(url, wait_selector='[data-auto="price-value"], script[type="application/ld+json"]')
            except ParserError:
                raise ParserError("YM: цена не найдена и Playwright недоступен/не помог")
            result = self._try_extract(resp.text)
            if result is not None:
                return result

        raise ParserError("YM: цена не найдена даже через Playwright")

    async def _fetch_html(self, url: str) -> tuple[str, str]:
        try:
            resp = await self._get(url)
            return resp.text, "http"
        except ParserError as e:
            # 403/4xx → сразу пробуем браузер
            try:
                resp = await self._get_browser(url, wait_selector='[data-auto="price-value"], script[type="application/ld+json"]')
                return resp.text, "browser"
            except ParserError:
                raise e

    def _try_extract(self, html: str) -> ParsedProduct | None:
        if "captcha" in html.lower() and "ld+json" not in html.lower():
            return None

        # 1. JSON-LD — самый надёжный источник
        jsonld = find_jsonld_product(html)
        if jsonld:
            result = self._from_jsonld(jsonld)
            if result is not None:
                return result

        # 2. Microdata / OG-теги + HTML-селекторы как fallback
        tree = HTMLParser(html)

        title = self._extract_title(tree)
        price = self._extract_price(tree, html)
        image = self._extract_image(tree)

        if price is None:
            return None

        return ParsedProduct(title=title, price=price, image_url=image)

    @staticmethod
    def _from_jsonld(data: dict) -> Optional[ParsedProduct]:
        offers = data.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        price = None
        if isinstance(offers, dict):
            price = to_decimal_price(
                offers.get("price")
                or offers.get("lowPrice")
                or offers.get("highPrice")
            )
        if price is None:
            return None

        image = data.get("image") or ""
        if isinstance(image, list):
            image = image[0] if image else ""
        if isinstance(image, str) and image.startswith("//"):
            image = "https:" + image

        return ParsedProduct(
            title=(data.get("name") or "Товар Я.Маркет").strip(),
            price=price,
            image_url=image or "",
        )

    @staticmethod
    def _extract_title(tree: HTMLParser) -> str:
        for selector in (
            'h1[data-auto="productCardTitle"]',
            'h1[data-zone-name="title"]',
            "h1",
            'meta[property="og:title"]',
        ):
            node = tree.css_first(selector)
            if not node:
                continue
            if selector.startswith("meta"):
                val = (node.attributes.get("content") or "").strip()
                if val:
                    return val
            else:
                val = node.text(strip=True)
                if val:
                    return val
        return "Товар Я.Маркет"

    @staticmethod
    def _extract_price(tree: HTMLParser, html: str) -> Optional[Decimal]:
        for selector in (
            '[data-auto="price-value"]',
            '[data-auto="snippet-price-current"]',
            '[data-zone-name="price"] [itemprop="price"]',
            'span[itemprop="price"]',
            'meta[itemprop="price"]',
        ):
            node = tree.css_first(selector)
            if not node:
                continue
            value = (
                node.attributes.get("content")
                or node.attributes.get("data-value")
                or node.text()
            )
            price = to_decimal_price(value)
            if price is not None and price > 0:
                return price

        # Last resort: ищем в HTML "999 ₽" / "999 руб"
        m = re.search(r'"price"\s*:\s*"?(\d[\d\s.,]*)"?', html)
        if m:
            return to_decimal_price(m.group(1))
        return None

    @staticmethod
    def _extract_image(tree: HTMLParser) -> str:
        for selector in (
            'img[data-auto="product-image"]',
            'meta[property="og:image"]',
            'link[rel="image_src"]',
        ):
            node = tree.css_first(selector)
            if not node:
                continue
            url = (
                node.attributes.get("src")
                or node.attributes.get("content")
                or node.attributes.get("href")
                or ""
            )
            if url:
                if url.startswith("//"):
                    url = "https:" + url
                return url
        return ""
