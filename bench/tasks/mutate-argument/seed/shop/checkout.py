"""The checkout page."""

from __future__ import annotations

from shop.cart import Cart


def summary(cart: Cart) -> str:
    """One line per product, then the total."""
    rows = [f"{line.sku} x{line.quantity}: {line.unit_price:.2f}" for line in cart.lines]
    return "\n".join([*rows, f"total: {cart.total:.2f}"])
