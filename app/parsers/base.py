from abc import ABC, abstractmethod

import httpx

from app.schemas import ParsedProduct


class ParserError(Exception):
    """Парсер не смог получить данные."""


class BaseParser(ABC):
    marketplace: str = ""
    timeout: float = 15.0

    headers: dict = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """Подходит ли парсер под этот URL."""

    @abstractmethod
    async def parse(self, url: str) -> ParsedProduct:
        """Получить данные о товаре."""

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
            resp = await client.get(url, **kwargs)
            resp.raise_for_status()
            return resp