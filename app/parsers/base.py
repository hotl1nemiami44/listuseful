from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import httpx

from app.schemas import ParsedProduct

logger = logging.getLogger(__name__)


class ParserError(Exception):
    """Парсер не смог получить данные."""


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class BaseParser(ABC):
    marketplace: str = ""
    timeout: float = 20.0

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
    ) -> httpx.Response:
        merged = {**self.headers, **(headers or {})}
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=merged,
            follow_redirects=True,
            http2=False,
        ) as client:
            resp = await client.get(url, params=params)
            if resp.status_code >= 400:
                raise ParserError(
                    f"{self.marketplace}: HTTP {resp.status_code} от {resp.request.url}"
                )
            return resp


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
