"""Discounts printed on price tags."""

from __future__ import annotations


def discounted_price(price: float, *, percent: float) -> float:
    """`price` lowered by `percent` per cent."""
    return round(price * (1 - percent / 100), 2)
