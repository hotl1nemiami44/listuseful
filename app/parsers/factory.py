from app.parsers.base import BaseParser, ParserError
from app.parsers.wildberries import WildberriesParser
from app.parsers.ozon import OzonParser
from app.parsers.yandex_market import YandexMarketParser
from app.parsers.aliexpress import AliexpressParser


PARSERS: list[type[BaseParser]] = [
    WildberriesParser,
    OzonParser,
    YandexMarketParser,
    AliexpressParser,
]


def get_parser(url: str) -> BaseParser:
    for parser_cls in PARSERS:
        if parser_cls.matches(url):
            return parser_cls()
    raise ParserError(f"Не найден парсер для URL: {url}")