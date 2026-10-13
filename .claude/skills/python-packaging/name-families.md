# Families of Names

Two names of the same shape for the same kind of job make that shape the rule for the third
(`naming.md`). The shapes worth copying, from the libraries whose surface is used most:

- **Namespace prefix** — `model_validate`, `model_dump`, `model_copy`, `model_json_schema`: every
  method of `BaseModel` is prefixed so a user's own field named `dump` can never collide.
- **Scope pair** — `field_validator` / `model_validator`: same job, two scopes, one word apart.
- **Derive a copy** — `with_only_columns`, `with_for_update`, `Path.with_suffix`: `with_` returns a
  copy with X set or replaced.
- **Plurality** — `scalar` / `scalars`: singular returns one, plural returns many.
- **Opposites are symmetrical** — `open`/`close`, `add`/`remove`, `get_label_style` /
  `set_label_style`, `correlate` / `correlate_except`: one part differs, the rest reads the same.

### A new public name takes the shape of its family

**Why:** a user who has learned one member predicts the next; an outlier is looked up every time,
and renaming it later costs a deprecation cycle (`naming.md`).

**Example:**
```python
# WRONG — three operations on one cache, three shapes
@final
class TileCache:
    def __init__(self, *, store: TileStore) -> None:
        self._store = store

    def get_tile(self, key: TileKey) -> Tile | None:
        return self._store.read(key)

    def tile_put(self, key: TileKey, tile: Tile) -> None:
        self._store.write(key, tile)

    def evict(self, key: TileKey) -> None:
        self._store.delete(key)


# CORRECT — one verb per operation, the noun in the same place
@final
class TileCache:
    def __init__(self, *, store: TileStore) -> None:
        self._store = store

    def get_tile(self, key: TileKey) -> Tile | None:
        return self._store.read(key)

    def put_tile(self, key: TileKey, tile: Tile) -> None:
        self._store.write(key, tile)

    def evict_tile(self, key: TileKey) -> None:
        self._store.delete(key)
```
