"""What the shop answers about orders."""

from __future__ import annotations

from shop.customers import CustomerRepo
from shop.orders import OrderRepo
from shop.products import ProductRepo


class OrderService:
    """Describes orders for the people who placed them."""

    def __init__(self, *, orders: OrderRepo, products: ProductRepo, customers: CustomerRepo) -> None:
        self._orders = orders
        self._products = products
        self._customers = customers

    def summary(self, order_id: int) -> str:
        """"<email> bought <product>"; `NotFoundError` if the order, its product or its customer is unknown."""
        order = self._orders.get(order_id)
        product = self._products.get(order.product_id)
        customer = self._customers.get(order.customer_id)
        return f"{customer.email} bought {product.name}"
