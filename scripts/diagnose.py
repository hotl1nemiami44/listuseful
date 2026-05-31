#!/usr/bin/env python
"""Диагностика парсеров. Запусти и пришли вывод, если что-то не работает.

    python scripts/diagnose.py
    python scripts/diagnose.py https://www.wildberries.ru/catalog/968907071/detail.aspx
"""
import asyncio
import sys

# Чтобы скрипт работал из корня репозитория
sys.path.insert(0, ".")

from app.parsers.base import _HAVE_CURL, _HAVE_PLAYWRIGHT, _HAVE_CRAWL4AI, _CA_BUNDLE  # noqa: E402
from app.parsers.factory import get_parser  # noqa: E402

DEFAULT_URLS = [
    "https://www.wildberries.ru/catalog/968907071/detail.aspx",
    "https://www.ozon.ru/product/test-1234567890/",
    "https://market.yandex.ru/product--test/123456",
    "https://aliexpress.ru/item/1005006172908860.html",
]

# Несколько вариантов эндпоинта/хоста — покажем, какой отвечает 200
WB_ENDPOINTS = [
    ("card.wb.ru   v2/detail min", "https://card.wb.ru/cards/v2/detail",
     {"appType": "1", "curr": "rub", "dest": "-1257786"}),
    ("u-card.wb.ru v2/detail min", "https://u-card.wb.ru/cards/v2/detail",
     {"appType": "1", "curr": "rub", "dest": "-1257786"}),
    ("card.wb.ru   v1/detail",     "https://card.wb.ru/cards/detail",
     {"appType": "1", "curr": "rub", "dest": "-1257786"}),
    ("u-card.wb.ru v1/detail",     "https://u-card.wb.ru/cards/detail",
     {"appType": "1", "curr": "rub", "dest": "-1257786"}),
    ("card.wb.ru   v2/list min",   "https://card.wb.ru/cards/v2/list",
     {"appType": "1", "curr": "rub", "dest": "-1257786"}),
]


async def probe_raw_wb(sku: str) -> None:
    """Прямые запросы к WB API разными способами — показываем сырой ответ."""
    print(f"\n--- Сырые запросы WB API (nm={sku}) ---")
    params = {"appType": "1", "curr": "rub", "dest": "-1257786", "spp": "30", "nm": sku}
    url = "https://card.wb.ru/cards/v2/detail"

    # httpx
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            r = await c.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
            print(f"  httpx     v2/detail: HTTP {r.status_code}, длина {len(r.text)}")
    except Exception as e:
        print(f"  httpx:     ОШИБКА {type(e).__name__}: {e}")

    # curl_cffi (синхронный API + фикс CA-пути) — перебираем эндпоинты
    if _HAVE_CURL:
        from curl_cffi import requests as cr
        verify = _CA_BUNDLE if _CA_BUNDLE is not None else False
        for name, ep, base in WB_ENDPOINTS:
            p = dict(base, nm=sku)
            try:
                r = cr.get(ep, params=p, timeout=15, impersonate="chrome", verify=verify)
                server = r.headers.get("server") or r.headers.get("Server") or "?"
                preview = r.text[:120].replace("\n", " ") if r.status_code == 200 else ""
                print(f"  {name}: HTTP {r.status_code} [server={server}] длина={len(r.text)} {preview}")
            except Exception as e:
                print(f"  {name}: ОШИБКА {type(e).__name__}: {str(e)[:80]}")

    # Дополнительно: статический CDN — должен быть доступен ВСЕГДА (без антибота)
    print("\n--- WB CDN (basket-NN.wbbasket.ru, статика) ---")
    if _HAVE_CURL:
        from curl_cffi import requests as cr
        from app.parsers.wildberries import WildberriesParser
        verify = _CA_BUNDLE if _CA_BUNDLE is not None else False
        basket = WildberriesParser._basket(sku)
        vol = int(sku) // 100_000
        part = int(sku) // 1000
        url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
        try:
            r = cr.get(url, timeout=15, impersonate="chrome", verify=verify)
            preview = r.text[:120].replace("\n", " ") if r.status_code == 200 else ""
            print(f"  basket-{basket} card.json: HTTP {r.status_code}  длина={len(r.text)}  {preview}")
        except Exception as e:
            print(f"  basket card.json: ОШИБКА {type(e).__name__}: {str(e)[:80]}")
    else:
        print("  curl_cffi: не установлен")


def probe_network_identity() -> None:
    """Показывает реальный исходящий IP и страну — ключевой фактор для WB.
    WB/Ozon режут зарубежные IP, поэтому если страна не RU — парсеры будут
    блокироваться независимо от кода."""
    import os
    print("\n--- Сеть ---")
    proxies = {k: os.environ.get(k) for k in
               ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")}
    active = {k: v for k, v in proxies.items() if v}
    print(f"  Системный прокси (env): {active or 'нет'}")
    try:
        from app.config import settings
        print(f"  proxy_url в .env:       {settings.proxy_url or 'нет'}")
    except Exception:
        pass

    if not _HAVE_CURL:
        return
    try:
        from curl_cffi import requests as cr
        verify = _CA_BUNDLE if _CA_BUNDLE is not None else False
        r = cr.get("http://ip-api.com/json/?fields=query,country,countryCode,isp",
                   timeout=15, impersonate="chrome", verify=verify)
        if r.status_code == 200:
            d = r.json()
            flag = "✅ RU" if d.get("countryCode") == "RU" else "❌ НЕ RU"
            print(f"  Твой IP:   {d.get('query')}")
            print(f"  Страна:    {d.get('country')} ({d.get('countryCode')})  {flag}")
            print(f"  Провайдер: {d.get('isp')}")
            if d.get("countryCode") != "RU":
                print("  ⚠️  IP не российский — WB/Ozon будут блокировать запросы.")
                print("      Выключи VPN или укажи российский proxy_url в .env")
        else:
            print(f"  Гео-сервис вернул HTTP {r.status_code}")
    except Exception as e:
        print(f"  Не удалось определить IP: {type(e).__name__}: {str(e)[:80]}")


async def main() -> None:
    print("=" * 60)
    print("ОКРУЖЕНИЕ")
    print("=" * 60)
    print(f"  curl_cffi:  {'есть' if _HAVE_CURL else 'НЕТ'}")
    print(f"  playwright: {'есть' if _HAVE_PLAYWRIGHT else 'НЕТ'}")
    print(f"  crawl4ai:   {'есть' if _HAVE_CRAWL4AI else 'НЕТ'}")

    probe_network_identity()

    urls = sys.argv[1:] or DEFAULT_URLS

    # Если передан WB-URL — покажем сырой ответ API
    for u in urls:
        if "wildberries.ru" in u or "wb.ru" in u:
            import re
            m = re.search(r"/catalog/(\d+)", u)
            if m:
                await probe_raw_wb(m.group(1))
            break

    print("\n" + "=" * 60)
    print("ПАРСЕРЫ")
    print("=" * 60)
    for url in urls:
        print(f"\n>>> {url}")
        try:
            parser = get_parser(url)
            result = await parser.parse(url)
            print(f"    OK [{parser.marketplace}]")
            print(f"    Название: {result.title}")
            print(f"    Цена:     {result.price} ₽")
            print(f"    Картинка: {result.image_url}")
        except Exception as e:
            print(f"    ОШИБКА: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
