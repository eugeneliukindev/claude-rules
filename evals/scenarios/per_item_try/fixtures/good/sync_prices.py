import logging
from collections.abc import Iterable

from store import PriceStore
from supplier import SupplierClient, SupplierError

logger = logging.getLogger(__name__)


def sync_prices(supplier: SupplierClient, store: PriceStore, skus: Iterable[str]) -> int:
    updated = 0
    for sku in skus:
        try:
            price = supplier.fetch_price(sku)
        except SupplierError:
            logger.warning("price skipped", extra={"sku": sku})
            continue
        store.update_price(sku, price)
        updated += 1
    return updated
