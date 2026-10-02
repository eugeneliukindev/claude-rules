"""Product records and the store contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Product:
    sku: str
    name: str
    price: Decimal


class ProductStore(ABC):
    @abstractmethod
    def save(self, product: Product) -> None: ...
