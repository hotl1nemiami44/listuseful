from .wildberries import WildberriesParser
from .ozon import OzonParser
from .yandex_market import YandexMarketParser
from .aliexpress import AliexpressParser
from .base import ProductInfo

PARSERS = {
    "wildberries": WildberriesParser(),
    "ozon": OzonParser(),
    "yandex_market": YandexMarketParser(),
    "aliexpress": AliexpressParser(),
}

async def fetch_product(marketplace: str, article: str):
    parser = PARSERS.get(marketplace)
    if not parser:
        return None
    return await parser.fetch(article)
