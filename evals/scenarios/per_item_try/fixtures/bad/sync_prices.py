import logging
from collections.abc import Iterable

from store import PriceStore
from supplier import SupplierClient, SupplierError

logger = logging.getLogger(__name__)


def sync_prices(supplier: SupplierClient, store: PriceStore, skus: Iterable[str]) -> int:
    updated = 0
    try:
        for sku in skus:
            store.update_price(sku, supplier.fetch_price(sku))
            updated += 1
    except SupplierError:
        logger.exception("sync failed")
    return updated
