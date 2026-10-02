import dataclasses
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Address:
    street: str
    city: str


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class Quote:
    carrier: str
    price: Decimal
    delivery_days: int


def find_cheapest(quotes: list[Quote]) -> Quote:
    return min(quotes, key=lambda quote: quote.price)
