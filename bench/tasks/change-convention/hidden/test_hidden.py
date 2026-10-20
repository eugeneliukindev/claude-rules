"""Hidden checks for change-convention: every lookup raises NotFoundError, none returns None."""

import ast
from pathlib import Path

import pytest

from shop.customers import CustomerRepo
from shop.errors import NotFoundError, ShopError
from shop.orders import Order, OrderRepo
from shop.products import ProductRepo
from shop.service import OrderService


@pytest.mark.parametrize("repo", [ProductRepo, CustomerRepo, OrderRepo])
def test_gate_missing_lookup_raises(repo: type) -> None:
    assert issubclass(NotFoundError, ShopError)
    with pytest.raises(NotFoundError):
        repo().get(404)


def test_gate_summary_of_unknown_order_raises() -> None:
    service = OrderService(orders=OrderRepo(), products=ProductRepo(), customers=CustomerRepo())
    with pytest.raises(NotFoundError):
        service.summary(404)


def test_gate_summary_with_unknown_product_raises() -> None:
    orders = OrderRepo()
    orders.put(Order(id=3, product_id=1, customer_id=2))
    service = OrderService(orders=orders, products=ProductRepo(), customers=CustomerRepo())
    with pytest.raises(NotFoundError):
        service.summary(3)


def test_design_no_lookup_is_annotated_optional() -> None:
    optional = []
    for path in Path("shop").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef) and node.returns is not None and "None" in ast.unparse(node.returns):
                if node.name not in {"__init__", "put"}:
                    optional.append(f"{path.name}:{node.name}")
    assert not optional, f"still returning None: {optional}"
