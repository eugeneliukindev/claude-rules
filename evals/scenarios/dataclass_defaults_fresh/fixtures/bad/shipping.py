from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Address:
    street: str
    city: str


@dataclass
class Quote:
    carrier: str
    price: Decimal
    delivery_days: int
