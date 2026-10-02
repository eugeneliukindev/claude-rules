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
    for row in _read_rows(source):
        price = _parse_price(row["price"])
        if not row["sku"].strip() or price is None:
            skipped += 1
            continue
        store.save(Product(sku=row["sku"].strip(), name=row["name"], price=price))
        imported += 1
    _log_summary(imported, skipped)


def _read_rows(source: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(source.open(newline="", encoding="utf-8")))


def _parse_price(text: str) -> Decimal | None:
    try:
        price = Decimal(text)
    except InvalidOperation:
        return None
    return price if price > 0 else None


def _log_summary(imported: int, skipped: int) -> None:
    """Log how the import ended.

    Both counts are logged so that an empty import can be told apart
    from one where every row was rejected.
    """
    logger.info("products imported", extra={"imported": imported, "skipped": skipped})
