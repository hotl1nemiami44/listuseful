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


def probe_dns_and_cert() -> None:
    """Проверяет DNS + TLS-сертификат для основных доменов WB.
    Если у пользователя стоит антивирус с HTTPS-перехватом или провайдер
    режет домен через DPI/DNS-spoofing — это сразу будет видно: либо
    сертификат не валидируется (CERT_VERIFY_FAILED), либо его эмитент
    окажется чем-то типа 'Kaspersky' / 'ESET' вместо реального CA."""
    import socket
    import ssl
    print("\n--- DNS + TLS сертификаты ---")
    hosts = ["card.wb.ru", "u-card.wb.ru", "basket-41.wbbasket.ru", "search.wb.ru"]
    for host in hosts:
        try:
            ip = socket.gethostbyname(host)
        except Exception as e:
            print(f"  {host:30s} DNS ОШИБКА: {type(e).__name__}: {e}")
            continue
        # Сначала проверяем с полной валидацией. Если перехвата нет — здесь же
        # достаём issuer (валидный dict только при CERT_REQUIRED).
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    issuer_str = (
                        issuer.get("commonName")
                        or issuer.get("organizationName")
                        or "?"
                    )
                    print(f"  {host:30s} IP={ip:15s} ✅ TLS OK  CA: {issuer_str}")
        except ssl.SSLCertVerificationError as e:
            # Это самый громкий сигнал: сертификат не валидируется системным CA.
            # 99% случаев — антивирус с HTTPS-перехватом или DPI/спуфинг.
            print(f"  {host:30s} IP={ip:15s} ❌ MITM/перехват: {str(e)[:100]}")
            # Достаём сам подменённый сертификат, чтобы показать его эмитента.
            try:
                ctx2 = ssl.create_default_context()
                ctx2.check_hostname = False
                ctx2.verify_mode = ssl.CERT_NONE
                with socket.create_connection((host, 443), timeout=10) as s2:
                    with ctx2.wrap_socket(s2, server_hostname=host) as ss2:
                        der = ss2.getpeercert(binary_form=True)
                        # Грубо вытаскиваем CN из DER — без cryptography:
                        # ищем все commonName-OID-фрагменты в дампе.
                        import re
                        text = der.decode("latin1", errors="ignore")
                        cns = re.findall(r"[\x20-\x7e]{6,}", text)
                        cn_hint = next(
                            (s for s in cns if any(k in s.lower()
                            for k in ("kaspersky", "eset", "drweb", "avast",
                                     "dr.web", "antivirus", "proxy", "filter"))),
                            cns[0] if cns else "?",
                        )
                        print(f"  {' '*30}   подменённый CN/строка: {cn_hint[:80]}")
            except Exception as inner:
                print(f"  {' '*30}   не удалось прочитать сертификат: {inner}")
        except Exception as e:
            print(f"  {host:30s} IP={ip:15s} TLS ОШИБКА: {type(e).__name__}: {str(e)[:60]}")


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
                # Показываем тело ВСЕХ ответов — у 4xx из API часто JSON с диагностикой
                preview = r.text[:200].replace("\n", " ").strip()
                print(f"  {name}: HTTP {r.status_code} [server={server}] длина={len(r.text)}")
                if preview:
                    print(f"      тело: {preview}")
            except Exception as e:
                print(f"  {name}: ОШИБКА {type(e).__name__}: {str(e)[:80]}")

    # Session-priming: вдруг card.wb.ru хочет куки, выданные главной страницей.
    # Открываем сессию, заходим на wildberries.ru, потом с теми же куками — в API.
    print("\n--- WB: проба с куками главной страницы (session priming) ---")
    if _HAVE_CURL:
        from curl_cffi import requests as cr
        verify = _CA_BUNDLE if _CA_BUNDLE is not None else False
        try:
            sess = cr.Session(impersonate="chrome")
            home = sess.get("https://www.wildberries.ru/", timeout=15, verify=verify)
            cookies = "; ".join(f"{c.name}={c.value}" for c in sess.cookies.jar)
            print(f"  GET wildberries.ru → HTTP {home.status_code}, куки: "
                  f"{len(list(sess.cookies.jar))} шт. [{cookies[:80]}]")
            r = sess.get(
                "https://card.wb.ru/cards/v2/detail",
                params={"appType": "1", "curr": "rub", "dest": "-1257786", "nm": sku},
                headers={"Origin": "https://www.wildberries.ru",
                         "Referer": "https://www.wildberries.ru/"},
                timeout=15, verify=verify,
            )
            preview = r.text[:160].replace("\n", " ").strip()
            print(f"  card.wb.ru с куками → HTTP {r.status_code}, длина {len(r.text)}")
            if preview:
                print(f"      тело: {preview}")
        except Exception as e:
            print(f"  ОШИБКА session priming: {type(e).__name__}: {str(e)[:80]}")

    # Брутфорс: ищем правильную корзину для этого vol — пробуем basket-01..basket-50
    print("\n--- WB CDN: ищем правильную корзину перебором ---")
    if _HAVE_CURL:
        from curl_cffi import requests as cr
        from app.parsers.wildberries import WildberriesParser
        verify = _CA_BUNDLE if _CA_BUNDLE is not None else False
        vol = int(sku) // 100_000
        part = int(sku) // 1000
        predicted = WildberriesParser._basket(sku)
        print(f"  vol={vol}, part={part}, моя таблица предсказывает basket-{predicted}")

        found = None
        for n in range(1, 51):
            basket = f"{n:02d}"
            url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
            try:
                r = cr.get(url, timeout=8, impersonate="chrome", verify=verify)
                if r.status_code == 200:
                    found = basket
                    preview = r.text[:150].replace("\n", " ")
                    print(f"  ✅ basket-{basket}: HTTP 200, длина {len(r.text)}")
                    print(f"      тело: {preview}")
                    break
            except Exception:
                continue
        if not found:
            print("  ❌ Ни одна корзина (1..50) не отдала 200")
            print("     → сетевая фильтрация режет *.wbbasket.ru, либо артикул удалён")


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
        # proxy/hosting/mobile — ключевые флаги: WB режет API для датацентровых IP.
        r = cr.get("http://ip-api.com/json/?fields=query,country,countryCode,isp,org,as,proxy,hosting,mobile",
                   timeout=15, impersonate="chrome", verify=verify)
        if r.status_code == 200:
            d = r.json()
            flag = "✅ RU" if d.get("countryCode") == "RU" else "❌ НЕ RU"
            print(f"  Твой IP:   {d.get('query')}")
            print(f"  Страна:    {d.get('country')} ({d.get('countryCode')})  {flag}")
            print(f"  Провайдер: {d.get('isp')}")
            print(f"  Орг/AS:    {d.get('org') or '-'} / {d.get('as') or '-'}")
            hosting = d.get("hosting")
            proxy = d.get("proxy")
            mobile = d.get("mobile")
            print(f"  Тип сети:  hosting={hosting}  proxy={proxy}  mobile={mobile}")
            if hosting or proxy:
                print("  🚫 IP помечен как ДАТАЦЕНТР/ПРОКСИ — именно поэтому WB отдаёт")
                print("     404/403/498 на API, но 200 на статическом CDN. WB режет")
                print("     не-резидентские IP. РЕШЕНИЕ: укажи РЕЗИДЕНТНЫЙ российский")
                print("     прокси в proxy_url (.env) или запусти с домашнего интернета.")
            elif d.get("countryCode") != "RU":
                print("  ⚠️  IP не российский — WB/Ozon будут блокировать запросы.")
                print("      Выключи VPN или укажи российский proxy_url в .env")
            else:
                print("  ✅ IP выглядит резидентным российским — блок не из-за IP.")
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
    probe_dns_and_cert()

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
