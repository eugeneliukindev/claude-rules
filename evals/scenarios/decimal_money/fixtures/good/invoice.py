import csv
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

VAT_RATE = Decimal("0.20")
CENT = Decimal("0.01")


def compute_totals(path: Path) -> tuple[Decimal, Decimal, Decimal]:
    with path.open(newline="") as handle:
        subtotal = sum(
            (Decimal(row["unit_price"]) * int(row["quantity"]) for row in csv.DictReader(handle)), Decimal(0)
        )
    vat = (subtotal * VAT_RATE).quantize(CENT, ROUND_HALF_EVEN)
    return subtotal.quantize(CENT), vat, (subtotal + vat).quantize(CENT)
