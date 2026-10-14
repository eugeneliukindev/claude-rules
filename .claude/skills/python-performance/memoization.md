# Memoization

### Only a pure module-level function of hashable arguments is memoized, with a stated bound

**Why:** an unbounded cache is a leak — bare `@lru_cache` is bounded at 128 entries, `@cache` not at
all. On a method the cache keeps every instance alive and grows per instance; ruff `B019` flags it.
A one-per-instance lazy value is a cached property; a cache across processes states its
invalidation rule in the design.

**Example:**
```python
# WRONG — the cache keeps every table it has seen alive, and never stops growing
@final
class OddsTable:
    def __init__(self, *, faces: int) -> None:
        self._faces = faces

    @cache
    def ways_to_roll(self, total: int, *, dice: int) -> int:
        if dice == 0:
            return 1 if total == 0 else 0
        face_values = range(1, self._faces + 1)
        return sum(self.ways_to_roll(total - face, dice=dice - 1) for face in face_values)


# CORRECT — a pure module-level function of hashable arguments, with a stated bound
@lru_cache(maxsize=_WAYS_CACHE_SIZE)
def ways_to_roll(total: int, *, dice: int, faces: int) -> int:
    if dice == 0:
        return 1 if total == 0 else 0
    face_values = range(1, faces + 1)
    return sum(ways_to_roll(total - face, dice=dice - 1, faces=faces) for face in face_values)
```
