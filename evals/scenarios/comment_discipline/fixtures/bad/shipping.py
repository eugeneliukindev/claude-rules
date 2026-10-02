"""Shipping fees for orders."""

import math
from decimal import Decimal


def shipping_fee(subtotal: Decimal, weight_kg: float, postcode: str) -> Decimal:
    """Return the shipping fee for an order.

    Called by the checkout service before the payment is captured.
    """
    # First we work out the surcharge.
    # Remote postcodes start with 9.
    # They pay 3.00 extra.
    # This applies even when shipping is free.
    surcharge = Decimal("3.00") if postcode.startswith("9") else Decimal(0)
    if subtotal >= Decimal("50.00"):
        return surcharge
    extra_kg = max(0, math.ceil(weight_kg - 2))
    return Decimal("4.90") + Decimal("1.20") * extra_kg + surcharge
