"""Price arithmetic for the shop."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

_CENT: Final = Decimal("0.01")


def add_vat(net_price: Decimal, vat_rate: Decimal) -> Decimal:
    return net_price * (1 + vat_rate)


def apply_discount(price: Decimal, discount_percent: Decimal) -> Decimal:
    return price * (1 - discount_percent / 100)


def round_to_cents(price: Decimal) -> Decimal:
    return price.quantize(_CENT, rounding=ROUND_HALF_UP)
