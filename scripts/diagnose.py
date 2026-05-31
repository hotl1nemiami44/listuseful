#!/usr/bin/env python
"""Диагностика парсеров. Запусти и пришли вывод, если что-то не работает.

    python scripts/diagnose.py
    python scripts/diagnose.py https://www.wildberries.ru/catalog/968907071/detail.aspx
"""
import asyncio
import sys

# Чтобы скрипт работал из корня репозитория
sys.path.insert(0, ".")

from app.parsers.base import _HAVE_CURL, _HAVE_PLAYWRIGHT, _HAVE_CRAWL4AI  # noqa: E402
from app.parsers.factory import get_parser  # noqa: E402

DEFAULT_URLS = [
    "https://www.wildberries.ru/catalog/968907071/detail.aspx",
    "https://www.ozon.ru/product/test-1234567890/",
    "https://market.yandex.ru/product--test/123456",
    "https://aliexpress.ru/item/1005006172908860.html",
]


async def probe_raw_wb(sku: str) -> None:
    """Прямой запрос к WB API — показываем сырой ответ."""
    print(f"\n--- Сырой запрос WB API (nm={sku}) ---")
    params = {"appType": "1", "curr": "rub", "dest": "-1257786", "spp": "30", "nm": sku}
    url = "https://card.wb.ru/cards/v2/detail"

    # httpx
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            r = await c.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
            print(f"  httpx:     HTTP {r.status_code}, длина {len(r.text)}")
            if r.status_code == 200:
                print(f"             {r.text[:160]}")
    except Exception as e:
        print(f"  httpx:     ОШИБКА {type(e).__name__}: {e}")

    # curl_cffi
    if _HAVE_CURL:
        try:
            from curl_cffi.requests import AsyncSession
            async with AsyncSession(timeout=15, impersonate="chrome") as s:
                r = await s.get(url, params=params)
                print(f"  curl_cffi: HTTP {r.status_code}, длина {len(r.text)}")
                if r.status_code == 200:
                    print(f"             {r.text[:160]}")
        except Exception as e:
            print(f"  curl_cffi: ОШИБКА {type(e).__name__}: {e}")
    else:
        print("  curl_cffi: не установлен")


async def main() -> None:
    print("=" * 60)
    print("ОКРУЖЕНИЕ")
    print("=" * 60)
    print(f"  curl_cffi:  {'есть' if _HAVE_CURL else 'НЕТ'}")
    print(f"  playwright: {'есть' if _HAVE_PLAYWRIGHT else 'НЕТ'}")
    print(f"  crawl4ai:   {'есть' if _HAVE_CRAWL4AI else 'НЕТ'}")

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
