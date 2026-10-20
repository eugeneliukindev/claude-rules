from decimal import Decimal

from shop.orders import Order


def test_order() -> None:
    assert Order(id=1, total=Decimal("9.99"), currency="EUR").total == Decimal("9.99")
