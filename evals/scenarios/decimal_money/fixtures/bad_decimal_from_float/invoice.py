from decimal import Decimal

VAT_RATE = Decimal(0.2)


def vat_for(subtotal: Decimal) -> Decimal:
    return (subtotal * VAT_RATE).quantize(Decimal("0.01"))
