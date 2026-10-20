"""Hidden checks for price-rounding: every price rounds half a cent up, like the till."""

import pytest


@pytest.mark.parametrize(("amount", "cents"), [(2.675, 2.68), (1.005, 1.01), (0.125, 0.13), (2.674, 2.67)])
def test_gate_round_price(amount: float, cents: float) -> None:
    from shop.money import round_price

    assert round_price(amount) == pytest.approx(cents, abs=1e-9)


def test_gate_invoice() -> None:
    from shop.cart import Line
    from shop.invoice import invoice_total

    assert invoice_total([Line(unit_price=2.675, quantity=1)], tax_rate=0.0) == pytest.approx(2.68)


def test_gate_cart_line() -> None:
    from shop.cart import Line

    assert Line(unit_price=0.335, quantity=3).total == pytest.approx(1.01)


def test_gate_discount_tag() -> None:
    from shop.discounts import discounted_price

    assert discounted_price(5.35, percent=50) == pytest.approx(2.68)


def test_refund_rounds_away_from_zero() -> None:
    from shop.money import round_price

    assert round_price(-2.675) == pytest.approx(-2.68)
