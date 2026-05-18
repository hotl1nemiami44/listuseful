from decimal import Decimal
from urllib.parse import urlparse

from app.parsers.base import BaseParser, ParserError
from app.schemas import ParsedProduct


class OzonParser(BaseParser):
    marketplace = "ozon"
    ENTRYPOINT = "https://api.ozon.ru/entrypoint-api.bx/page/json/v2"

    headers = {
        **BaseParser.headers,
        "Accept": "application/json",
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "ozon.ru" in url

    async def parse(self, url: str) -> ParsedProduct:
        path = urlparse(url).path  # /product/xxx-123456789/
        params = {"url": path}
        try:
            resp = await self._get(self.ENTRYPOINT, params=params)
            data = resp.json()
        except Exception as e:
            raise ParserError(f"Ozon: ошибка запроса: {e}") from e

        widget_states = data.get("widgetStates", {})

        title = None
        price = None
        image_url = ""

        # Перебираем виджеты — структура может меняться, ищем по ключам
        import json as _json
        for key, raw in widget_states.items():
            if not isinstance(raw, str):
                continue
            try:
                parsed = _json.loads(raw)
            except _json.JSONDecodeError:
                continue

            if key.startswith("webProductHeading") and not title:
                title = parsed.get("title")
            if key.startswith("webPrice") and price is None:
                # Цена в виде строки "1 299 ₽"
                p_str = parsed.get("cardPrice") or parsed.get("price") or ""
                digits = "".join(ch for ch in p_str if ch.isdigit())
                if digits:
                    price = Decimal(digits)
            if key.startswith("webGallery") and not image_url:
                images = parsed.get("images") or []
                if images:
                    image_url = images[0] if isinstance(images[0], str) else images[0].get("src", "")

        if price is None:
            raise ParserError("Ozon: цена не найдена (возможно нужен Playwright или прокси)")

        return ParsedProduct(
            title=(title or "Товар Ozon").strip(),
            price=price,
            image_url=image_url,
        )