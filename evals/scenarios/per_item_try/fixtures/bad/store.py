"""Our own price catalogue."""

from decimal import Decimal


class PriceStore:
    def __init__(self) -> None:
        self._prices: dict[str, Decimal] = {}

    def update_price(self, sku: str, price: Decimal) -> None:
        self._prices[sku] = price
