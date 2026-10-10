---
name: python-performance
description: >-
  Python performance work, measure first: profiling and benchmarking before optimizing, fixing the
  algorithm before the constants, the container chosen by its operation — deque, heapq, bisect,
  Counter, itertools.batched, array, memoryview — streaming instead of materializing, slots=True,
  functools.cache and lru_cache as a bounded contract and never on methods, precompiling and
  hoisting out of hot loops, and pinning a budget with a test so a regression fails a check. Use
  when Python code is slow or must be sped up, when asked to optimize, profile or benchmark it,
  when a list serves as a queue, a sort only takes the top k, or many numbers sit in memory, when
  reaching for functools.cache or lru_cache, or when reviewing a proposed optimization.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Performance

Algorithmic sanity — `slots=True` from the always-loaded rules, and the container chosen by its
operation below — needs no measurement; everything else here does.

- **Measure before optimizing.** Any performance change references a measurement — a profile for
  CPU, an allocation profile for memory, a benchmark to pin the improvement. An optimization
  without a before-and-after number is refactoring risk with no proven benefit.
- **Optimize the algorithm, then the constants.** A quadratic membership scan beats any
  micro-tuning: set and dict lookups, precomputed indexes, and batching are where real wins live.
  N+1 query patterns are bugs, not tuning opportunities.

  ```python
  # WRONG — a list membership test inside the loop: every order scans every blocked id
  blocked_user_ids = [user.user_id for user in blocked_users]
  held_orders = [order for order in orders if order.user_id in blocked_user_ids]

  # CORRECT — built once as a frozenset: each membership test is a hash lookup
  blocked_user_ids = frozenset(user.user_id for user in blocked_users)
  held_orders = [order for order in orders if order.user_id in blocked_user_ids]
  ```

- **Stream, don't materialize**: generators and chunked reads for anything larger than
  memory-trivial; never build a list from a stream just to iterate it once.

  ```python
  # WRONG — every row is held in memory at once, only to be summed
  with export_path.open(encoding="utf-8", newline="") as export_file:
      rows = list(csv.DictReader(export_file))
  total_cents = sum(int(row["amount_cents"]) for row in rows)

  # CORRECT — the reader yields one row at a time, and only the running sum is kept
  with export_path.open(encoding="utf-8", newline="") as export_file:
      total_cents = sum(int(row["amount_cents"]) for row in csv.DictReader(export_file))
  ```

- **The container is chosen by the operation it serves** — algorithmic sanity, so it needs no
  profile. `types.md` picks `tuple` and `frozenset` for immutability; this is the cost side.
  Measured on CPython 3.14:

  | the operation | use | instead of | measured |
  |---|---|---|---|
  | take from the front | `deque.popleft`; `deque(maxlen=n)` for a bounded buffer | `list.pop(0)`, which shifts every element | 100k items: 1.2 s → 6 ms |
  | the k largest or smallest | `heapq.nlargest` / `nsmallest` | `sorted(...)[:k]` | top 10 of 1M: 680 ms → 34 ms |
  | a position in sorted data — a tier, a bucket | `bisect.bisect_right` over a sorted tuple | a scan of the thresholds | 10k lookups in 1k: 550 ms → 3 ms |
  | count by key | `Counter(iterable)`, which counts in C | a dict and `if key in` | 1M items: 2× |
  | fixed-size groups from a stream | `itertools.batched(iterable, n)` (3.12+) | slicing a list, which must exist first | — |

  ```python
  # WRONG — a scan of every threshold for every order
  def discount_rate(order_total_cents: int) -> Decimal:
      tier = 0
      for threshold_cents in _TIER_THRESHOLDS_CENTS:
          if order_total_cents >= threshold_cents:
              tier += 1
      return _TIER_RATES[tier]

  # CORRECT — sorted thresholds, one fewer than the rates: bisect counts those passed in log n
  def discount_rate(order_total_cents: int) -> Decimal:
      return _TIER_RATES[bisect.bisect_right(_TIER_THRESHOLDS_CENTS, order_total_cents)]
  ```

- **Many numbers of one type are an `array`, not a list.** Every element of a `list[int]` or
  `list[float]` is an object of its own behind a pointer; `array("q")` and `array("d")` store eight
  bytes each in one buffer — a million latencies took 40 MB as a list and 8 MB as an array.
  Arithmetic over whole columns is numpy's job, a dependency a measurement decides.

  ```python
  # WRONG — a million int objects behind a million pointers
  latencies_ns: list[int] = []
  # CORRECT — eight bytes per sample, in one buffer
  latencies_ns = array("q")
  ```

- **Slicing `bytes` copies; slicing a `memoryview` does not.** Cutting 50 MB into 64 KiB chunks
  took 15.5 ms a pass as `bytes` slices and 0.2 ms as views, with no second copy alive. Release the
  view with `with`: while it exists, the buffer under it cannot be resized or freed.

  ```python
  # WRONG — every chunk is a fresh 64 KiB copy
  def write_in_chunks(payload: bytes, sink: BinaryIO) -> None:
      for offset in range(0, len(payload), _CHUNK_SIZE_BYTES):
          sink.write(payload[offset : offset + _CHUNK_SIZE_BYTES])

  # CORRECT — the slices point into payload, and the view is released on the way out
  def write_in_chunks(payload: bytes, sink: BinaryIO) -> None:
      with memoryview(payload) as view:
          for offset in range(0, len(view), _CHUNK_SIZE_BYTES):
              sink.write(view[offset : offset + _CHUNK_SIZE_BYTES])
  ```

- **`slots=True` is the `types.md` default**, and a hand-written class with fixed attributes gets
  `__slots__` for the same reasons: less memory per instance and faster attribute access. Skip it
  only for classes needing dynamic attributes, framework classes that require `__dict__`, and
  `cached_property` users. Multiple inheritance works when at most one base has non-empty slots —
  a mixin declares `__slots__ = ()` — and **every** base must declare them: one utility base
  without `__slots__` once gave every class below it a `__dict__` back, silently. `slotscheck` in
  the lint step finds both.
- **Caching is a contract, not a sprinkle.** Memoize only **pure** functions of hashable arguments,
  with an explicit bound — an unbounded cache is a leak. **Never on methods**: the cache keeps the
  instance alive and grows per instance; cache a module-level function, or use a cached property
  for a one-per-instance lazy value. Any cross-process cache states its invalidation rule in the
  design, or it is a stale-data bug scheduled for later — cache design and cachetools are in
  `python-caching`, redis in `python-redis`. Bare `@lru_cache` is bounded at 128
  entries, `@cache` is not bounded at all; ruff `B019` flags either one on a method.

  ```python
  # WRONG — the cache keeps every parser it has seen alive, and never stops growing
  class AddressParser:
      @cache
      def normalize_postcode(self, raw_postcode: str) -> Postcode: ...

  # CORRECT — a pure module-level function of hashable arguments, with a stated bound
  @lru_cache(maxsize=4096)
  def normalize_postcode(raw_postcode: str) -> Postcode: ...
  ```

- **Precompile and hoist**: compiled patterns at module level; no attribute chain or dict lookup
  repeated in a hot loop that a local would hoist.

  ```python
  # WRONG — re.findall looks the pattern up in re's cache on every call
  def find_order_ids(text: str) -> list[str]:
      return re.findall(r"ORD-\d{8}", text)

  # CORRECT — compiled once at import, and named for what it matches
  _ORDER_ID_PATTERN: Final = re.compile(r"ORD-\d{8}")

  def find_order_ids(text: str) -> list[str]:
      return _ORDER_ID_PATTERN.findall(text)
  ```

- **Concurrency follows the workload**, and is measured before assuming parallelism helps — pool
  and pickling overhead is real.
- **Performance-sensitive paths are marked and tested** with a stated budget, so a regression fails
  a check instead of arriving as an incident. **The budget is in a unit that does not vary** —
  statements per request, calls to the expensive operation, allocations — never wall time, which
  is noise on a shared runner and blind to a regression smaller than the noise.

```python
# WRONG — flaky on a shared runner, and a page that doubles its queries still passes
def test_order_page_is_fast(client: TestClient) -> None:
    started_seconds = time.perf_counter()
    client.get("/orders")

    assert time.perf_counter() - started_seconds < _ORDER_PAGE_BUDGET_SECONDS

# CORRECT — the same budget in statements, counted by a fixture (python-sqlalchemy)
def test_order_page_is_fast(client: TestClient, statements: list[str]) -> None:
    client.get("/orders")

    assert len(statements) <= _ORDER_PAGE_STATEMENTS
```
