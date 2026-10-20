"""Hidden checks for mutate-argument: the coupon gives a new cart and leaves the old one as it was."""

import pytest

from shop.cart import Cart, Line


def _cart() -> Cart:
    return Cart([Line(sku="tea", unit_price=4.0, quantity=2), Line(sku="mug", unit_price=10.0)])


def test_gate_coupon_lowers_prices() -> None:
    from shop.coupons import with_coupon

    assert with_coupon(_cart(), 10).total == pytest.approx(16.2)


def test_design_original_cart_is_untouched() -> None:
    from shop.coupons import with_coupon

    cart = _cart()
    with_coupon(cart, 10)
    assert cart.total == pytest.approx(18.0)
    assert [line.unit_price for line in cart.lines] == [4.0, 10.0]
