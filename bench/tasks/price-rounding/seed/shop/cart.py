"""Lines of a shopping cart."""

from __future__ import annotations

from dataclasses import dataclass

from shop.money import round_price


@dataclass(frozen=True, slots=True, kw_only=True)
class Line:
    """One product in the cart."""

    unit_price: float
    quantity: int

    @property
    def total(self) -> float:
        """What the line costs."""
        return round_price(self.unit_price * self.quantity)
