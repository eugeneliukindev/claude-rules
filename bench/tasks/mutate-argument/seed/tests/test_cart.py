from shop.cart import Cart, Line


def test_total() -> None:
    cart = Cart()
    cart.add(Line(sku="tea", unit_price=4.0, quantity=2))
    assert cart.total == 8.0
