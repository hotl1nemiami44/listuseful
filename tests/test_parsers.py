import pytest

from app.parsers.factory import get_parser
from app.parsers.base import ParserError


def test_factory_picks_wb():
    p = get_parser("https://www.wildberries.ru/catalog/12345678/detail.aspx")
    assert p.marketplace == "wb"


def test_factory_picks_ozon():
    p = get_parser("https://www.ozon.ru/product/something-123456789/")
    assert p.marketplace == "ozon"


def test_factory_picks_ym():
    p = get_parser("https://market.yandex.ru/product--xxx/12345")
    assert p.marketplace == "ym"


def test_factory_picks_ali():
    p = get_parser("https://aliexpress.ru/item/1005006.html")
    assert p.marketplace == "ali"


def test_factory_unknown():
    with pytest.raises(ParserError):
        get_parser("https://example.com/product/1")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_wb_real_request():
    """Реальный запрос к WB. Запускать вручную: pytest -m integration"""
    p = get_parser("https://www.wildberries.ru/catalog/123456789/detail.aspx")
    result = await p.parse("https://www.wildberries.ru/catalog/123456789/detail.aspx")
    assert result.price > 0
    assert result.title