"""Coupons that lower the prices in a cart."""

from __future__ import annotations

from shop.cart import Cart


def with_coupon(cart: Cart, percent: float) -> Cart:
    """`cart` with every price lowered by `percent` per cent."""
    for line in cart.lines:
        line.unit_price *= 1 - percent / 100
    return cart
