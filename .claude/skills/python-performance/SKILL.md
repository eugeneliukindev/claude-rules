---
name: python-performance
description: >-
  Python performance work, measure first: profiling and benchmarking before optimizing, fixing the
  algorithm before the constants, streaming instead of materializing, slots=True, functools.cache
  and lru_cache as a bounded contract and never on methods, precompiling and hoisting out of hot
  loops, and pinning a budget with a test so a regression fails a check. Use when Python code is
  slow or must be sped up, when asked to optimize, profile or benchmark it, when reaching for
  functools.cache or lru_cache, or when reviewing a proposed optimization.
---

# Performance

Algorithmic sanity and `slots=True` are defaults in the always-loaded rules and need no measurement;
everything here does.

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
  design, or it is a stale-data bug scheduled for later. Bare `@lru_cache` is bounded at 128
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
