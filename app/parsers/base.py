from __future__ import annotations

import json
import logging
import os
import re
import shutil
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.schemas import ParsedProduct

logger = logging.getLogger(__name__)

# curl_cffi подделывает TLS-fingerprint реального Chrome (JA3/JA4),
# чем обходит антибот WB/Ozon/Я.Маркета — обычный httpx с его TLS они режут.
# Импорт ленивый, чтобы тесты не требовали curl_cffi.
try:
    from curl_cffi.requests import AsyncSession as _CurlSession
    _HAVE_CURL = True
except Exception:  # pragma: no cover - окружения без curl_cffi
    _CurlSession = None
    _HAVE_CURL = False

# httpx — резервный путь, если curl_cffi недоступен.
import httpx

# certifi обеспечивает рабочие CA-сертификаты для curl_cffi.
import certifi


def _safe_ca_bundle() -> Optional[str]:
    """Возвращает путь к CA-бандлу, который libcurl сможет прочитать.

    На Windows libcurl падает с `curl: (77)`, если путь к .pem содержит
    не-ASCII символы (например, кириллица в имени пользователя:
    C:\\Users\\Глеб\\...). В этом случае копируем бандл в ASCII-папку
    (C:\\Users\\Public). Если не получилось — вернём None, и вызывающий
    код отключит проверку сертификата.
    """
    try:
        path = certifi.where()
    except Exception:
        return None
    try:
        path.encode("ascii")
        return path  # путь уже безопасный (обычный случай на Linux/macOS)
    except UnicodeEncodeError:
        pass

    candidates = []
    if os.environ.get("PUBLIC"):  # C:\Users\Public — всегда ASCII и доступна на запись
        candidates.append(os.path.join(os.environ["PUBLIC"], "price_tracker_cacert.pem"))
    if os.environ.get("SystemRoot"):
        candidates.append(os.path.join(os.environ["SystemRoot"], "Temp", "price_tracker_cacert.pem"))
    candidates.append(os.path.join(os.path.abspath(os.sep), "price_tracker_cacert.pem"))

    for dest in candidates:
        try:
            dest.encode("ascii")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(path, dest)
            return dest
        except Exception:
            continue
    return None


# Вычисляем один раз при импорте
_CA_BUNDLE = _safe_ca_bundle()

# Playwright — резерв на случай отсутствия crawl4ai.
try:
    from playwright.async_api import async_playwright
    _HAVE_PLAYWRIGHT = True
except Exception:  # pragma: no cover
    async_playwright = None
    _HAVE_PLAYWRIGHT = False

# crawl4ai — основной браузерный путь. Async-native, stealth-mode + magic-mode +
# simulate_user из коробки, обходит большинство антиботов на маркетплейсах.
# Под капотом Playwright, но с правильно настроенным fingerprinting.
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    _HAVE_CRAWL4AI = True
except Exception:  # pragma: no cover
    AsyncWebCrawler = None
    BrowserConfig = None
    CrawlerRunConfig = None
    CacheMode = None
    _HAVE_CRAWL4AI = False


class ParserError(Exception):
    """Парсер не смог получить данные."""


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Версия Chrome для импersonation в curl_cffi (TLS + HTTP/2 fingerprint)
CURL_IMPERSONATE = "chrome124"


class _Response:
    """Унифицированный ответ — у curl_cffi и httpx разные API."""

    __slots__ = ("status_code", "text", "_json", "url")

    def __init__(self, status_code: int, text: str, url: str, json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data
        self.url = url

    def json(self):
        if self._json is not None:
            return self._json
        return json.loads(self.text)


class BaseParser(ABC):
    marketplace: str = ""
    timeout: float = 25.0

    headers: dict = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """Подходит ли парсер под этот URL."""

    @abstractmethod
    async def parse(self, url: str) -> ParsedProduct:
        """Получить данные о товаре."""

    async def _get(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> _Response:
        merged = {**self.headers, **(headers or {})}
        if _HAVE_CURL:
            return await self._get_curl(url, headers=merged, params=params)
        return await self._get_httpx(url, headers=merged, params=params)

    async def _get_curl(self, url: str, *, headers: dict, params: Optional[dict]) -> _Response:
        # verify: сначала пытаемся с CA-бандлом (безопасно), при ошибке
        # сертификата — без проверки (curl (77) из-за не-ASCII пути на Windows).
        verify: Any = _CA_BUNDLE if _CA_BUNDLE is not None else False
        last_exc: Optional[Exception] = None

        # impersonate-таргет может отсутствовать в конкретной сборке curl_cffi —
        # пробуем настроенный, затем дефолтный "chrome", затем без impersonate.
        for target in (CURL_IMPERSONATE, "chrome", None):
            kwargs: dict = {"timeout": self.timeout, "verify": verify}
            if target:
                kwargs["impersonate"] = target
            try:
                async with _CurlSession(**kwargs) as session:
                    resp = await session.get(
                        url, headers=headers, params=params, allow_redirects=True
                    )
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                # Ошибка сертификата → переключаемся на verify=False и пробуем снова
                if verify is not False and (
                    "certificate" in msg or "(77)" in msg or "cacert" in msg or "ssl" in msg
                ):
                    verify = False
                continue

            if resp.status_code >= 400:
                raise ParserError(
                    f"{self.marketplace}: HTTP {resp.status_code} от {resp.url}"
                )
            return _Response(resp.status_code, resp.text, str(resp.url))

        raise ParserError(
            f"{self.marketplace}: curl_cffi не смог выполнить запрос: {last_exc}"
        )

    async def _get_httpx(self, url: str, *, headers: dict, params: Optional[dict]) -> _Response:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=headers,
            follow_redirects=True,
            http2=False,
        ) as client:
            try:
                resp = await client.get(url, params=params)
            except Exception as e:
                raise ParserError(f"{self.marketplace}: сетевая ошибка: {e}") from e
            if resp.status_code >= 400:
                raise ParserError(
                    f"{self.marketplace}: HTTP {resp.status_code} от {resp.request.url}"
                )
            return _Response(resp.status_code, resp.text, str(resp.request.url))

    async def _get_browser(self, url: str, *, wait_selector: Optional[str] = None) -> _Response:
        """Браузерный фолбэк через crawl4ai (или raw Playwright если crawl4ai нет).

        crawl4ai даёт stealth-mode, magic-mode и simulate_user из коробки —
        это пробивает антибот WB/Ozon/Я.Маркета. Требует установки браузера:
        `crawl4ai-setup` (одна команда поставит и Playwright, и Chromium).
        """
        if _HAVE_CRAWL4AI:
            return await self._get_crawl4ai(url, wait_selector=wait_selector)
        if _HAVE_PLAYWRIGHT:
            return await self._get_playwright(url, wait_selector=wait_selector)
        raise ParserError(
            f"{self.marketplace}: ни crawl4ai, ни Playwright не установлены — "
            "выполни `pip install crawl4ai && crawl4ai-setup`"
        )

    async def _get_crawl4ai(self, url: str, *, wait_selector: Optional[str] = None) -> _Response:
        browser_cfg = BrowserConfig(
            headless=True,
            user_agent=DEFAULT_UA,
            viewport_width=1920,
            viewport_height=1080,
            enable_stealth=True,  # маскировка navigator.webdriver и др.
            extra_args=["--lang=ru-RU"],
            verbose=False,
        )
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="domcontentloaded",
            page_timeout=int(self.timeout * 1000),
            # Если селектор задан — ждём его; иначе даём JS-рендеру время.
            wait_for=f"css:{wait_selector}" if wait_selector else None,
            wait_for_timeout=8000,
            delay_before_return_html=0.5 if wait_selector else 3.5,
            simulate_user=True,     # эмуляция движения мыши/скроллов
            magic=True,             # auto-bypass для популярных антиботов
            override_navigator=True,
            remove_overlay_elements=True,
            scan_full_page=True,    # триггерит ленивую загрузку контента
            locale="ru-RU",
            verbose=False,
        )
        try:
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                result = await crawler.arun(url=url, config=run_cfg)
        except ParserError:
            raise
        except Exception as e:
            raise ParserError(f"{self.marketplace}: crawl4ai ошибка: {e}") from e

        if not result.success:
            raise ParserError(
                f"{self.marketplace}: crawl4ai не получил страницу: "
                f"{getattr(result, 'error_message', 'unknown')}"
            )
        status = getattr(result, "status_code", 200) or 200
        if status >= 400:
            raise ParserError(f"{self.marketplace}: crawl4ai HTTP {status} от {url}")
        return _Response(status, result.html or "", result.url or url)

    async def _get_playwright(self, url: str, *, wait_selector: Optional[str] = None) -> _Response:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        user_agent=DEFAULT_UA,
                        locale="ru-RU",
                        viewport={"width": 1920, "height": 1080},
                        extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
                    )
                    page = await context.new_page()
                    response = await page.goto(url, timeout=int(self.timeout * 1000), wait_until="domcontentloaded")
                    if wait_selector:
                        try:
                            await page.wait_for_selector(wait_selector, timeout=8000)
                        except Exception:
                            pass
                    html = await page.content()
                    status = response.status if response else 200
                    final_url = page.url
                finally:
                    await browser.close()
        except ParserError:
            raise
        except Exception as e:
            raise ParserError(f"{self.marketplace}: Playwright ошибка: {e}") from e

        if status >= 400:
            raise ParserError(f"{self.marketplace}: Playwright HTTP {status} от {final_url}")
        return _Response(status, html, final_url)


_PRICE_CLEAN_RE = re.compile(r"[^\d.,]")


def to_decimal_price(value: Any) -> Optional[Decimal]:
    """Парсит цену из строки/числа в Decimal с двумя знаками."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    if not isinstance(value, str):
        return None
    s = _PRICE_CLEAN_RE.sub("", value).replace(",", ".")
    # На случай нескольких точек ("1.299.00") — оставляем последнюю как разделитель копеек
    if s.count(".") > 1:
        head, _, tail = s.rpartition(".")
        s = head.replace(".", "") + "." + tail
    if not s or s == ".":
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def find_jsonld_product(html: str) -> Optional[dict]:
    """Находит первый JSON-LD блок с @type=Product (или содержащий offers)."""
    for raw in _JSON_LD_RE.findall(html):
        text = raw.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Иногда внутри ld+json экранированы переводы строк — пробуем мягко
            try:
                data = json.loads(text.replace("\n", " "))
            except json.JSONDecodeError:
                continue
        for candidate in _walk_jsonld(data):
            t = candidate.get("@type")
            if t == "Product" or (isinstance(t, list) and "Product" in t):
                return candidate
            if "offers" in candidate and ("name" in candidate or "title" in candidate):
                return candidate
    return None


def _walk_jsonld(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_jsonld(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_jsonld(v)


def extract_balanced_json(text: str, start: int) -> Optional[str]:
    """Возвращает подстроку с валидным JSON-объектом, начиная с позиции `{` или `[`."""
    if start >= len(text):
        return None
    opener = text[start]
    if opener not in "{[":
        return None
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
