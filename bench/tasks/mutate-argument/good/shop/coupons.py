"""Coupons that lower the prices in a cart."""

from __future__ import annotations

from dataclasses import replace

from shop.cart import Cart


def with_coupon(cart: Cart, percent: float) -> Cart:
    """A copy of `cart` with every price lowered by `percent` per cent."""
    factor = 1 - percent / 100
    return Cart([replace(line, unit_price=line.unit_price * factor) for line in cart.lines])
