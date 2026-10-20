from shop.customers import Customer, CustomerRepo
from shop.orders import Order, OrderRepo
from shop.products import Product, ProductRepo
from shop.service import OrderService


def test_summary_names_customer_and_product() -> None:
    orders, products, customers = OrderRepo(), ProductRepo(), CustomerRepo()
    products.put(Product(id=1, name="lamp"))
    customers.put(Customer(id=2, email="a@example.com"))
    orders.put(Order(id=3, product_id=1, customer_id=2))
    service = OrderService(orders=orders, products=products, customers=customers)
    assert service.summary(3) == "a@example.com bought lamp"
