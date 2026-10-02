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
- **Stream, don't materialize**: generators and chunked reads for anything larger than
  memory-trivial; never build a list from a stream just to iterate it once.
- **`slots=True` on every dataclass** — and `__slots__` on hand-written classes with fixed
  attributes — as the default, not an optimization: less memory per instance, faster attribute
  access, and typo-attributes become errors. `slots` is about the *attribute set*, `frozen` about
  *mutability*; real immutability needs both. Skip slots only for classes needing dynamic
  attributes, multiple inheritance from slotted bases, framework classes that require `__dict__`,
  and cached-property users.
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
- **Concurrency follows the workload**, and is measured before assuming parallelism helps — pool
  and pickling overhead is real.
- **Performance-sensitive paths are marked and tested** with a stated budget, so a regression fails
  a check instead of arriving as an incident.
