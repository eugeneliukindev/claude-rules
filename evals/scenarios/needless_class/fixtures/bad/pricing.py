"""Price arithmetic for the shop."""

from decimal import ROUND_HALF_UP, Decimal


class PriceCalculator:
    @staticmethod
    def add_vat(net_price: Decimal, vat_rate: Decimal) -> Decimal:
        return net_price * (1 + vat_rate)

    @staticmethod
    def apply_discount(price: Decimal, discount_percent: Decimal) -> Decimal:
        return price * (1 - discount_percent / 100)

    @staticmethod
    def round_to_cents(price: Decimal) -> Decimal:
        return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
