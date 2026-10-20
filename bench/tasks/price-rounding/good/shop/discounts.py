"""Discounts printed on price tags."""

from __future__ import annotations

from shop.money import round_price


def discounted_price(price: float, *, percent: float) -> float:
    """`price` lowered by `percent` per cent."""
    return round_price(price * (1 - percent / 100))
