"""Orders the shop keeps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Order:
    """One order."""

    id: int
    product_id: int
    customer_id: int


class OrderRepo:
    """Orders kept in memory."""

    def __init__(self) -> None:
        self._items: dict[int, Order] = {}

    def put(self, item: Order) -> None:
        """Store `item`, replacing one with the same id."""
        self._items[item.id] = item

    def get(self, item_id: int) -> Order | None:
        """The order with this id, or `None`."""
        return self._items.get(item_id)
