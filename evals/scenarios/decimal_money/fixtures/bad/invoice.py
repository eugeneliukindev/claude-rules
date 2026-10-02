import csv


def compute_totals(path: str) -> tuple[float, float, float]:
    with open(path, newline="") as handle:
        subtotal = sum(float(row["unit_price"]) * int(row["quantity"]) for row in csv.DictReader(handle))
    vat = round(subtotal * 0.2, 2)
    return round(subtotal, 2), vat, round(subtotal + vat, 2)
