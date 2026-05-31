import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.parsers.aliexpress import AliexpressParser
from app.parsers.base import (
    ParserError,
    extract_balanced_json,
    find_jsonld_product,
    to_decimal_price,
)
from app.parsers.factory import get_parser
from app.parsers.ozon import OzonParser
from app.parsers.wildberries import WildberriesParser
from app.parsers.yandex_market import YandexMarketParser


# ---------- factory ----------

def test_factory_picks_wb():
    assert get_parser("https://www.wildberries.ru/catalog/12345678/detail.aspx").marketplace == "wb"


def test_factory_picks_ozon():
    assert get_parser("https://www.ozon.ru/product/something-123456789/").marketplace == "ozon"


def test_factory_picks_ym():
    assert get_parser("https://market.yandex.ru/product--xxx/12345").marketplace == "ym"


def test_factory_picks_ali():
    assert get_parser("https://aliexpress.ru/item/1005006.html").marketplace == "ali"


def test_factory_unknown():
    with pytest.raises(ParserError):
        get_parser("https://example.com/product/1")


# ---------- helpers ----------

def test_to_decimal_price_basic():
    assert to_decimal_price("1 299 ₽") == Decimal("1299")
    assert to_decimal_price("1 299,50 ₽") == Decimal("1299.50")
    assert to_decimal_price("1.299,00") == Decimal("1299.00")
    assert to_decimal_price(199) == Decimal("199")
    assert to_decimal_price(None) is None
    assert to_decimal_price("---") is None


def test_extract_balanced_json():
    s = 'prefix={"a": 1, "b": {"c": 2}};suffix'
    start = s.index("{")
    assert extract_balanced_json(s, start) == '{"a": 1, "b": {"c": 2}}'

    nested = '{"k":"}{"}'   # строки игнорируются
    assert extract_balanced_json(nested, 0) == nested


def test_find_jsonld_product():
    html = """
    <html><head>
    <script type="application/ld+json">{"@type":"Product","name":"X","offers":{"price":"1990"}}</script>
    </head></html>
    """
    data = find_jsonld_product(html)
    assert data is not None
    assert data["name"] == "X"
    assert data["offers"]["price"] == "1990"


# ---------- WB ----------

def test_wb_extract_sku_catalog():
    assert WildberriesParser._extract_sku("https://www.wildberries.ru/catalog/123/detail.aspx") == "123"


def test_wb_extract_sku_card_param():
    assert WildberriesParser._extract_sku("https://www.wildberries.ru/product?card=999") == "999"


def test_wb_extract_sku_missing():
    with pytest.raises(ParserError):
        WildberriesParser._extract_sku("https://www.wildberries.ru/about")


def test_wb_basket_mapping():
    # vol = 0 → basket 01
    assert WildberriesParser._basket("100") == "01"
    # vol = 200 → basket 02
    assert WildberriesParser._basket("20000000") == "02"
    # vol = 5000 → basket 27 (5000 <= 5189)
    assert WildberriesParser._basket("500000000") == "27"
    # vol = 9689 (реальный высокий артикул) → basket 36
    assert WildberriesParser._basket("968907071") == "36"
    # vol сверху — последняя корзина
    assert WildberriesParser._basket("999999999999") == "40"


def test_wb_image_url():
    url = WildberriesParser._image_url("123456789")
    assert url.startswith("https://basket-")
    assert "/vol1234/part123456/123456789/" in url


def test_wb_extract_price_new_schema():
    product = {"sizes": [{"price": {"product": 129900, "total": 149900}}]}
    assert WildberriesParser._extract_price(product) == Decimal("1299.00")


def test_wb_extract_price_legacy_kopecks():
    assert WildberriesParser._extract_price({"salePriceU": 89900}) == Decimal("899.00")


def test_wb_extract_price_string_fallback():
    assert WildberriesParser._extract_price({"price": "2 499 ₽"}) == Decimal("2499")


def test_wb_extract_price_missing():
    assert WildberriesParser._extract_price({"name": "x"}) is None


@pytest.mark.asyncio
async def test_wb_parse_full(monkeypatch):
    parser = WildberriesParser()

    class FakeResp:
        def json(self_):
            return {
                "data": {
                    "products": [
                        {
                            "name": "Кружка керамическая",
                            "brand": "MyBrand",
                            "sizes": [{"price": {"product": 49900}}],
                        }
                    ]
                }
            }

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(WildberriesParser, "_get", fake_get)
    result = await parser.parse("https://www.wildberries.ru/catalog/123456789/detail.aspx")
    assert result.title == "MyBrand Кружка керамическая"
    assert result.price == Decimal("499.00")
    assert "123456789" in result.image_url


@pytest.mark.asyncio
async def test_wb_falls_back_through_endpoints(monkeypatch):
    """Первый эндпоинт даёт ошибку — парсер должен попробовать следующий."""
    parser = WildberriesParser()
    calls = []

    class GoodResp:
        def json(self_):
            return {"data": {"products": [{"name": "X", "sizes": [{"price": {"product": 10000}}]}]}}

    async def fake_get(self_, url, **kw):
        calls.append(url)
        if url == WildberriesParser.CARD_ENDPOINTS[0]:
            raise ParserError("WB: HTTP 404 ...")
        return GoodResp()

    monkeypatch.setattr(WildberriesParser, "_get", fake_get)
    result = await parser.parse("https://www.wildberries.ru/catalog/100/detail.aspx")
    assert result.price == Decimal("100.00")
    assert len(calls) == 2  # первый упал, второй сработал


@pytest.mark.asyncio
async def test_wb_all_endpoints_fail(monkeypatch):
    parser = WildberriesParser()

    async def fake_get(self_, url, **kw):
        raise ParserError("WB: HTTP 404 ...")

    async def fake_browser(self_, url, **kw):
        raise ParserError("WB: Playwright не установлен")

    monkeypatch.setattr(WildberriesParser, "_get", fake_get)
    monkeypatch.setattr(WildberriesParser, "_get_browser", fake_browser)
    with pytest.raises(ParserError):
        await parser.parse("https://www.wildberries.ru/catalog/100/detail.aspx")


@pytest.mark.asyncio
async def test_wb_browser_fallback_when_api_404(monkeypatch):
    """Все JSON-эндпоинты дают 404 — парсер должен забрать цену со страницы."""
    parser = WildberriesParser()

    async def fake_get(self_, url, **kw):
        raise ParserError("WB: HTTP 404 ...")

    product_html = """
        <html><body>
          <h1 class="product-page__title">Наушники беспроводные</h1>
          <ins class="price-block__final-price">2 499 ₽</ins>
        </body></html>
    """

    async def fake_browser(self_, url, **kw):
        from app.parsers.base import _Response
        return _Response(200, product_html, url)

    monkeypatch.setattr(WildberriesParser, "_get", fake_get)
    monkeypatch.setattr(WildberriesParser, "_get_browser", fake_browser)
    result = await parser.parse("https://www.wildberries.ru/catalog/968907071/detail.aspx")
    assert result.title == "Наушники беспроводные"
    assert result.price == Decimal("2499")
    assert "968907071" in result.image_url


# ---------- Ozon ----------

def test_ozon_price_from_widget_card():
    parsed = {"cardPrice": "1 299 ₽", "price": "1 499 ₽"}
    assert OzonParser._price_from_widget(parsed) == Decimal("1299")


def test_ozon_price_from_widget_nested():
    parsed = {"price": {"price": "999 ₽"}}
    assert OzonParser._price_from_widget(parsed) == Decimal("999")


def test_ozon_price_from_widget_missing():
    assert OzonParser._price_from_widget({"foo": "bar"}) is None


def test_ozon_image_from_widget():
    assert OzonParser._image_from_widget({"images": ["https://example.com/a.jpg"]}) == "https://example.com/a.jpg"
    assert OzonParser._image_from_widget({"coverImage": {"src": "https://x/y.jpg"}}) == "https://x/y.jpg"


@pytest.mark.asyncio
async def test_ozon_parse_via_api(monkeypatch):
    parser = OzonParser()
    fake_widgets = {
        "webProductHeading-1": json.dumps({"title": "Смартфон XYZ"}),
        "webPrice-1": json.dumps({"cardPrice": "29 990 ₽", "price": "32 990 ₽"}),
        "webGallery-1": json.dumps({"images": [{"src": "https://cdn/x.jpg"}]}),
    }

    class FakeResp:
        def json(self_):
            return {"widgetStates": fake_widgets}

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(OzonParser, "_get", fake_get)
    result = await parser.parse("https://www.ozon.ru/product/test-1/")
    assert result.title == "Смартфон XYZ"
    assert result.price == Decimal("29990")
    assert result.image_url == "https://cdn/x.jpg"


@pytest.mark.asyncio
async def test_ozon_falls_back_to_jsonld(monkeypatch):
    parser = OzonParser()

    class JsonResp:
        def json(self_):
            return {"widgetStates": {}}

    class HtmlResp:
        text = """
            <script type="application/ld+json">
            {"@type":"Product","name":"Чайник","offers":{"price":"2490"},"image":"https://x/a.jpg"}
            </script>
        """

    async def fake_get(self_, url, **kw):
        return JsonResp() if url == OzonParser.ENTRYPOINT else HtmlResp()

    monkeypatch.setattr(OzonParser, "_get", fake_get)
    result = await parser.parse("https://www.ozon.ru/product/test-1/")
    assert result.title == "Чайник"
    assert result.price == Decimal("2490")
    assert result.image_url == "https://x/a.jpg"


# ---------- AliExpress ----------

@pytest.mark.asyncio
async def test_ali_parses_jsonld(monkeypatch):
    parser = AliexpressParser()
    html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"Наушники","offers":{"price":"1234.50"},"image":["https://x/h.jpg"]}
        </script>
    """

    class FakeResp:
        text = html

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(AliexpressParser, "_get", fake_get)
    result = await parser.parse("https://aliexpress.ru/item/1.html")
    assert result.title == "Наушники"
    assert result.price == Decimal("1234.50")
    assert result.image_url == "https://x/h.jpg"


@pytest.mark.asyncio
async def test_ali_parses_run_params(monkeypatch):
    parser = AliexpressParser()
    payload = {
        "data": {
            "titleModule": {"subject": "Лампа"},
            "priceModule": {"minActivityAmount": {"value": 599}},
            "imageModule": {"imagePathList": ["https://x/l.jpg"]},
        }
    }
    html = f"<script>window.runParams = {json.dumps(payload)};</script>"

    class FakeResp:
        text = html

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(AliexpressParser, "_get", fake_get)
    result = await parser.parse("https://aliexpress.com/item/1.html")
    assert result.title == "Лампа"
    assert result.price == Decimal("599")
    assert result.image_url == "https://x/l.jpg"


@pytest.mark.asyncio
async def test_ali_parses_dc_data(monkeypatch):
    parser = AliexpressParser()
    payload = {
        "productData": {
            "title": "Кабель USB-C",
            "sku": {"def": {"promotionPrice": {"minPrice": 199.0}}},
            "images": ["https://x/c.jpg"],
        }
    }
    html = f"<script>_d_c_.DCData = {json.dumps(payload)};</script>"

    class FakeResp:
        text = html

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(AliexpressParser, "_get", fake_get)
    result = await parser.parse("https://aliexpress.ru/item/1.html")
    assert result.title == "Кабель USB-C"
    assert result.price == Decimal("199.0")
    assert result.image_url == "https://x/c.jpg"


@pytest.mark.asyncio
async def test_ali_no_data_raises(monkeypatch):
    parser = AliexpressParser()

    class FakeResp:
        text = "<html><body>nothing here</body></html>"

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(AliexpressParser, "_get", fake_get)
    with pytest.raises(ParserError):
        await parser.parse("https://aliexpress.ru/item/1.html")


# ---------- Yandex Market ----------

@pytest.mark.asyncio
async def test_ym_parses_jsonld(monkeypatch):
    parser = YandexMarketParser()
    html = """
        <html><body>
        <script type="application/ld+json">
        {"@type":"Product","name":"Робот-пылесос","offers":{"price":"15990"},
         "image":"//avatars.mds.yandex.net/x.jpg"}
        </script>
        </body></html>
    """

    class FakeResp:
        text = html

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(YandexMarketParser, "_get", fake_get)
    result = await parser.parse("https://market.yandex.ru/product--xxx/123")
    assert result.title == "Робот-пылесос"
    assert result.price == Decimal("15990")
    assert result.image_url.startswith("https://")


@pytest.mark.asyncio
async def test_ym_html_fallback(monkeypatch):
    parser = YandexMarketParser()
    html = """
        <html><body>
        <h1 data-auto="productCardTitle">Кофеварка</h1>
        <span data-auto="price-value">7 990 ₽</span>
        <meta property="og:image" content="https://x/cf.jpg" />
        </body></html>
    """

    class FakeResp:
        text = html

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(YandexMarketParser, "_get", fake_get)
    result = await parser.parse("https://market.yandex.ru/product--xxx/123")
    assert result.title == "Кофеварка"
    assert result.price == Decimal("7990")
    assert result.image_url == "https://x/cf.jpg"


@pytest.mark.asyncio
async def test_ym_captcha_raises(monkeypatch):
    parser = YandexMarketParser()

    class FakeResp:
        text = "<html>Please solve the CAPTCHA</html>"

    async def fake_get(self_, url, **kw):
        return FakeResp()

    monkeypatch.setattr(YandexMarketParser, "_get", fake_get)
    with pytest.raises(ParserError):
        await parser.parse("https://market.yandex.ru/product--xxx/123")
