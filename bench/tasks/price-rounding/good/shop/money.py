"""Money arithmetic shared by the cart, the invoice and the discounts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def round_price(amount: float) -> float:
    """`amount` rounded to whole cents, half a cent up, as the till does."""
    return float(Decimal(str(amount)).quantize(CENT, rounding=ROUND_HALF_UP))
