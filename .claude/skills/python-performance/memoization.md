# Memoization

### Only a pure module-level function of hashable arguments is memoized, with a stated bound

**Why:** an unbounded cache is a leak — bare `@lru_cache` is bounded at 128 entries, `@cache` not at
all. On a method the cache keeps every instance alive and grows per instance; ruff `B019` flags it.
A one-per-instance lazy value is a cached property; a cache across processes states its
invalidation rule in the design.

**Example:**
```python
# WRONG — the cache keeps every parser it has seen alive, and never stops growing
class AddressParser:
    @cache
    def normalize_postcode(self, raw_postcode: str) -> Postcode:
        return Postcode(raw_postcode.replace(" ", "").upper())


# CORRECT — a pure module-level function of hashable arguments, with a stated bound
@lru_cache(maxsize=_POSTCODE_CACHE_SIZE)
def normalize_postcode(raw_postcode: str) -> Postcode:
    return Postcode(raw_postcode.replace(" ", "").upper())
```
