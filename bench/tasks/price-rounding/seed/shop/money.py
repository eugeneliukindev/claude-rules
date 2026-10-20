"""Money arithmetic shared by the cart, the invoice and the discounts."""

from __future__ import annotations


def round_price(amount: float) -> float:
    """`amount` rounded to whole cents."""
    return round(amount, 2)
