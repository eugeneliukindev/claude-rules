"""Customers the shop keeps."""

from __future__ import annotations

from dataclasses import dataclass

from shop.errors import NotFoundError


@dataclass(frozen=True, slots=True, kw_only=True)
class Customer:
    """One customer."""

    id: int
    email: str


class CustomerRepo:
    """Customers kept in memory."""

    def __init__(self) -> None:
        self._items: dict[int, Customer] = {}

    def put(self, item: Customer) -> None:
        """Store `item`, replacing one with the same id."""
        self._items[item.id] = item

    def get(self, item_id: int) -> Customer:
        """The customer with this id; `NotFoundError` if there is none."""
        if item_id not in self._items:
            raise NotFoundError(item_id)
        return self._items[item_id]
