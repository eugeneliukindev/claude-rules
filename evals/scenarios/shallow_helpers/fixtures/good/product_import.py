"""Import products from a CSV export."""

import csv
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from store import Product, ProductStore

logger = logging.getLogger(__name__)


def import_products(store: ProductStore, source: Path) -> None:
    imported = 0
    skipped = 0
    with source.open(newline="", encoding="utf-8") as rows:
        for row in csv.DictReader(rows):
            price = _parse_price(row["price"])
            if not row["sku"].strip() or price is None:
                skipped += 1
                continue
            store.save(Product(sku=row["sku"].strip(), name=row["name"], price=price))
            imported += 1

    logger.info("products imported", extra={"imported": imported, "skipped": skipped})


def _parse_price(text: str) -> Decimal | None:
    try:
        price = Decimal(text)
    except InvalidOperation:
        return None
    return price if price > 0 else None
