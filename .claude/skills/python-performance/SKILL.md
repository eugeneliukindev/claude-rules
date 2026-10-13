---
name: python-performance
description: >-
  Speeds Python up by measurement: profile first, fix the algorithm, pick the container by its
  operation, stream instead of materializing, cache with bounds, pin a budget with a test. Use
  when code is slow or must be optimized, profiled or benchmarked, a list serves as a queue, many
  numbers sit in memory, or functools.cache is considered.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Performance

Algorithmic sanity — the container chosen by its operation, `slots=True` from the always-loaded
rules — needs no measurement; everything else here does. Cache design and cachetools are
`python-caching`, redis `python-redis`; the statement-counting fixture is `python-sqlalchemy`.

## Measure First

### A performance change carries a measurement from before and after it

**Why:** an optimization without a number is refactoring risk with no proven benefit. CPU is a
profile — `python -m cProfile -o before.prof -m package.module`, read with `pstats` or `snakeviz`,
or `py-spy top --pid` on a running process; memory is two `tracemalloc` snapshots compared; the
number to pin is `timeit` or `pytest-benchmark`. One wall-clock reading of one run is noise, and
says nothing about where the time went. The profile goes with the change.

## Containers

| the operation | use | instead of | measured on CPython 3.14 |
|---|---|---|---|
| take from the front | `deque.popleft`; `deque(maxlen=n)` for a bounded buffer | `list.pop(0)`, which shifts every element | 100k items: 1.2 s → 6 ms |
| the k largest or smallest | `heapq.nlargest` / `nsmallest` | `sorted(...)[:k]` | top 10 of 1M: 680 ms → 34 ms |
| a position in sorted data — a tier, a bucket | `bisect.bisect_right` over a sorted tuple | a scan of the thresholds | 10k lookups in 1k: 550 ms → 3 ms |
| count by key | `Counter(iterable)`, which counts in C | a dict and `if key in` | 1M items: 2× |
| fixed-size groups from a stream | `itertools.batched(iterable, n)` | slicing a list, which must exist first | — |

### The container is chosen by the operation it serves

**Why:** the cost is in the operation, not the data — `list.pop(0)` shifts every element, a scan of
thresholds is linear where `bisect` is logarithmic. `types.md` picks `tuple` and `frozenset`
for immutability; this table is the cost side, and needs no profile.

**Example:**
```python
# WRONG — a scan of every threshold for every member
def loyalty_tier(points: int) -> Tier:
    tier_index = 0
    for threshold_points in _TIER_THRESHOLDS_POINTS:
        if points >= threshold_points:
            tier_index += 1
    return _TIERS[tier_index]


# CORRECT — sorted thresholds, one fewer than the tiers: bisect counts those passed in log n
def loyalty_tier(points: int) -> Tier:
    return _TIERS[bisect.bisect_right(_TIER_THRESHOLDS_POINTS, points)]
```

### `deque(maxlen=n)` is a window that drops its oldest, never a queue of work

**Why:** when full it discards from the other end without an error — right for recent samples where
losing the oldest is the point, silent data loss for pending work.

**Example:**
```python
# WRONG — a work queue with maxlen: the 1,001st pending import silently drops the oldest
@final
class ImportBacklog:
    def __init__(self, *, capacity: int = _BACKLOG_CAPACITY) -> None:
        self._pending_import_ids: deque[ImportId] = deque(maxlen=capacity)


# CORRECT — a window of recent latencies, where dropping the oldest is the stated policy
@final
class LatencyWindow:
    def __init__(self, *, size: int = _WINDOW_SIZE) -> None:
        self._recent_latencies_ns: deque[int] = deque(maxlen=size)
```

## Budgets

### A performance-sensitive path is tested with a budget in a unit that does not vary

**Why:** a regression then fails a check instead of arriving as an incident. The unit is statements
per request, calls to the expensive operation, allocations — never wall time, which is noise on a
shared runner and blind to a regression smaller than the noise.

**Example:**
```python
# WRONG — flaky on a shared runner, and a page that doubles its queries still passes
def test_article_page_stays_in_budget(client: TestClient) -> None:
    started_seconds = time.perf_counter()

    client.get("/articles")

    assert time.perf_counter() - started_seconds < _ARTICLE_PAGE_BUDGET_SECONDS


# CORRECT — the same budget in statements, counted by a fixture
def test_article_page_stays_in_budget(client: TestClient, statements: list[str]) -> None:
    client.get("/articles")

    assert len(statements) <= _ARTICLE_PAGE_STATEMENTS
```

## Memory

**Before holding many numbers, slicing large byte buffers, or writing a class that will have many
instances, read [memory.md](memory.md)** — `array` for numbers, `memoryview` for slices, `__slots__`
on every base of a hierarchy.

## Memoization

**Before reaching for `functools.cache` or `lru_cache`, read [memoization.md](memoization.md)** —
pure functions of hashable arguments, a stated bound, never on a method.