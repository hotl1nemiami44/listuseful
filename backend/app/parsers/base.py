from dataclasses import dataclass
from typing import Optional
from abc import ABC, abstractmethod

@dataclass
class ProductInfo:
    name: str
    price: float
    image_url: Optional[str]
    product_url: str
    currency: str = "RUB"

class BaseParser(ABC):
    @abstractmethod
    async def fetch(self, article: str) -> Optional[ProductInfo]:
        pass
