"""Products the shop keeps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Product:
    """One product."""

    id: int
    name: str


class ProductRepo:
    """Products kept in memory."""

    def __init__(self) -> None:
        self._items: dict[int, Product] = {}

    def put(self, item: Product) -> None:
        """Store `item`, replacing one with the same id."""
        self._items[item.id] = item

    def get(self, item_id: int) -> Product | None:
        """The product with this id, or `None`."""
        return self._items.get(item_id)
