# Locks and Shared State

No shared state at all is better than any lock here: a thread that owns its data and hands results
over through a queue needs none.

### State shared between threads is guarded by a `threading.Lock`; the GIL is not a lock

**Why:** a check-then-set on a shared dict races between threads today, and on a free-threaded
`3.13t` or `3.14t` build every compound operation does. A lock shared with coroutines on a loop is
`python-async`'s.

**Example:**
```python
# WRONG — two threads read the same count, and one download is never counted
@final
class DownloadCounter:
    def __init__(self) -> None:
        self._count_by_host: dict[str, int] = {}

    def record(self, host: str) -> None:
        self._count_by_host[host] = self._count_by_host.get(host, 0) + 1


# CORRECT — the read and the write happen under one lock
@final
class DownloadCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count_by_host: dict[str, int] = {}

    def record(self, host: str) -> None:
        with self._lock:
            self._count_by_host[host] = self._count_by_host.get(host, 0) + 1
```

### A lock covers the data, never the slow call that fills it

**Why:** a lock held across I/O makes every thread that wants any entry wait behind the slowest
fetch. The fetch runs outside; the lock covers the read and the write, and `setdefault` keeps the
first value if two threads fetched at once.

**Example:**
```python
# WRONG — every thread asking for any price waits behind one slow catalog call
@final
class PriceCache:
    def __init__(self, *, catalog: PriceCatalog) -> None:
        self._catalog = catalog
        self._lock = threading.Lock()
        self._price_by_sku: dict[Sku, Decimal] = {}

    def price(self, sku: Sku) -> Decimal:
        with self._lock:
            if sku not in self._price_by_sku:
                self._price_by_sku[sku] = self._catalog.fetch_price(sku)
            return self._price_by_sku[sku]


# CORRECT — the lock covers the dictionary only; the fetch runs outside it
@final
class PriceCache:
    def __init__(self, *, catalog: PriceCatalog) -> None:
        self._catalog = catalog
        self._lock = threading.Lock()
        self._price_by_sku: dict[Sku, Decimal] = {}

    def price(self, sku: Sku) -> Decimal:
        with self._lock:
            cached = self._price_by_sku.get(sku)
        if cached is not None:
            return cached
        fetched = self._catalog.fetch_price(sku)
        with self._lock:
            return self._price_by_sku.setdefault(sku, fetched)
```

### `threading.local` is for per-thread resources only, and thread-safety is documented

**Why:** in async code many tasks share one thread, so a thread-local leaks between them —
`contextvars` is the per-task store. A thread-local fits a resource that must not cross threads, a
connection a non-thread-safe driver hands out. Whether a class may be shared between threads is a
property its docstring states, never an assumption its callers make.
