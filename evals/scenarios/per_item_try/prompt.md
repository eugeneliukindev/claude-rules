Write `sync_prices.py` with the function our nightly job will call: given a `SupplierClient`
(`supplier.py`), a `PriceStore` (`store.py`) and the list of SKUs we sell (a few thousand), it
fetches the current supplier price of every SKU and updates our store, and returns how many prices
were updated. No need to run anything.
