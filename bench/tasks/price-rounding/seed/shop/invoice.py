"""The invoice a customer receives."""

from __future__ import annotations

from collections.abc import Sequence

from shop.cart import Line
from shop.money import round_price


def invoice_total(lines: Sequence[Line], *, tax_rate: float) -> float:
    """Sum of the lines with tax added."""
    net = sum(line.total for line in lines)
    return round_price(net * (1 + tax_rate))
