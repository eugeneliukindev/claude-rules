"""Shipping fees for orders."""

import math
from decimal import Decimal
from typing import Final

FREE_SHIPPING_THRESHOLD: Final = Decimal("50.00")
_BASE_FEE: Final = Decimal("4.90")
_BASE_WEIGHT_KG: Final = 2
_FEE_PER_EXTRA_KG: Final = Decimal("1.20")
_REMOTE_SURCHARGE: Final = Decimal("3.00")
_REMOTE_POSTCODE_PREFIX: Final = "9"


def shipping_fee(subtotal: Decimal, weight_kg: float, postcode: str) -> Decimal:
    """Return the shipping fee for an order."""
    # Remote delivery costs the carrier the same whether the order ships free or not:
    surcharge = _REMOTE_SURCHARGE if postcode.startswith(_REMOTE_POSTCODE_PREFIX) else Decimal(0)
    if subtotal >= FREE_SHIPPING_THRESHOLD:
        return surcharge

    extra_kg = max(0, math.ceil(weight_kg - _BASE_WEIGHT_KG))  # a started kilogram counts as whole
    return _BASE_FEE + _FEE_PER_EXTRA_KG * extra_kg + surcharge
