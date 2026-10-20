from shop.cart import Line
from shop.invoice import invoice_total


def test_line_total() -> None:
    assert Line(unit_price=2.5, quantity=2).total == 5.0


def test_invoice_adds_tax() -> None:
    assert invoice_total([Line(unit_price=10.0, quantity=1)], tax_rate=0.2) == 12.0
