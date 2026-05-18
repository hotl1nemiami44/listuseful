from decimal import Decimal

from selectolax.parser import HTMLParser

from app.parsers.base import BaseParser, ParserError
from app.schemas import ParsedProduct


class YandexMarketParser(BaseParser):
    marketplace = "ym"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "market.yandex.ru" in url

    async def parse(self, url: str) -> ParsedProduct:
        try:
            resp = await self._get(url)
        except Exception as e:
            raise ParserError(f"YM: ошибка запроса: {e}") from e

        tree = HTMLParser(resp.text)

        title_node = tree.css_first('h1[data-auto="productCardTitle"]') or tree.css_first("h1")
        title = title_node.text(strip=True) if title_node else "Товар Я.Маркет"

        price_node = tree.css_first('[data-auto="snippet-price-current"]') or tree.css_first('[data-auto="price-value"]')
        if not price_node:
            raise ParserError("YM: цена не найдена (вероятно сработала антибот-защита)")
        digits = "".join(ch for ch in price_node.text() if ch.isdigit())
        if not digits:
            raise ParserError("YM: не удалось распарсить цену")
        price = Decimal(digits)

        img_node = tree.css_first('img[data-auto="product-image"]') or tree.css_first('meta[property="og:image"]')
        image_url = ""
        if img_node:
            image_url = img_node.attributes.get("src") or img_node.attributes.get("content") or ""
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        return ParsedProduct(title=title, price=price, image_url=image_url)