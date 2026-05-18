import json
import re
from decimal import Decimal

from app.parsers.base import BaseParser, ParserError
from app.schemas import ParsedProduct


class AliexpressParser(BaseParser):
    marketplace = "ali"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "aliexpress." in url  # aliexpress.com / aliexpress.ru

    async def parse(self, url: str) -> ParsedProduct:
        try:
            resp = await self._get(url)
        except Exception as e:
            raise ParserError(f"Ali: ошибка запроса: {e}") from e

        html = resp.text
        # AliExpress кладёт данные товара в window.runParams = { data: {...} }
        m = re.search(r"window\.runParams\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
        if not m:
            raise ParserError("Ali: не нашли runParams (возможно требуется JS-рендеринг)")
        try:
            data = json.loads(m.group(1))
            payload = data.get("data", {})
        except json.JSONDecodeError as e:
            raise ParserError(f"Ali: не удалось распарсить JSON: {e}") from e

        title = (
            payload.get("titleModule", {}).get("subject")
            or payload.get("productInfoComponent", {}).get("subject")
            or "Товар AliExpress"
        )

        price_module = payload.get("priceModule", {}) or payload.get("priceComponent", {})
        price_info = (
            price_module.get("minActivityAmount")
            or price_module.get("minAmount")
            or price_module.get("formatedActivityPrice")
        )
        price = None
        if isinstance(price_info, dict) and "value" in price_info:
            price = Decimal(str(price_info["value"]))
        elif isinstance(price_info, str):
            digits = "".join(ch for ch in price_info if ch.isdigit() or ch == ".")
            if digits:
                price = Decimal(digits)

        if price is None:
            raise ParserError("Ali: цена не найдена")

        image_url = ""
        images = payload.get("imageModule", {}).get("imagePathList") or []
        if images:
            image_url = images[0]

        return ParsedProduct(title=title, price=price, image_url=image_url)