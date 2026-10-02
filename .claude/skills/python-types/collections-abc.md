# Choosing a `collections.abc` ABC

## Contents

- Annotations: the most abstract parameter type that works, the most concrete return type you build
- Runtime: `isinstance` against the ABC, never `hasattr` or `type()`
- Implementing a container: subclass the ABC, implement only the abstract methods
- Worked `# WRONG` / `# CORRECT` pair: a case-insensitive mapping
- Beyond `collections.abc`: `numbers`, `io`, `os.PathLike`, `contextlib`

The standard library already names "things you can iterate / index / call / hash". Use those names
in annotations, at runtime instead of `hasattr`, and instead of hand-rolled protocols.

**In annotations — accept the most abstract type that works, return the most concrete you build:**

| You only need to… | Annotate the parameter as | Never as |
|---|---|---|
| iterate once | `Iterable[T]` | `list[T]` |
| iterate, know the length, index | `Sequence[T]` | `list[T]`, `tuple[T, ...]` |
| mutate in place | `MutableSequence[T]` | `list[T]` |
| look up by key, iterate keys | `Mapping[K, V]` | `dict[K, V]` |
| add / remove keys | `MutableMapping[K, V]` | `dict[K, V]` |
| test membership, no duplicates | `Set[T]` (alias `AbstractSet`) | `set[T]`, `frozenset[T]` |
| call it with one argument | `Callable[[A], R]` — two or more: a calling `Protocol` | `object` |
| pass to `len()` | `Sized` | — |
| use as a dict key | `Hashable` | — |
| call `next()` / `send()` on it | `Iterator[T]` / `Generator[Y, S, R]` | `list[T]` |
| `async for` | `AsyncIterable[T]` / `AsyncIterator[T]` | — |
| `await` | `Awaitable[T]` / `Coroutine[…]` | — |
| read/write bytes or text | `typing.IO[bytes]`, `typing.TextIO` | `object` |
| a real number, `int` included | `float` (accepts `int`, PEP 484) | `numbers.Real` |

- Import from `collections.abc`, never from `typing` — those aliases are deprecated.
- Returns are concrete: `-> list[User]`, `-> dict[str, int]`. Return an ABC only when deliberately
  hiding the container (`-> Iterator[Row]` for a generator, `-> Mapping[…]` for a read-only view).
- `Sequence[str]` is also how you say "a list of strings but **not** a bare `str`" — mypy treats
  `str` as `Sequence[str]`, so add an `isinstance(value, str)` guard when a bare string is a bug.
- Attributes and dataclass fields follow the same rule: `items: Sequence[Item]` for read-only,
  `items: list[Item]` only when the class itself mutates it.
- `numbers.Real` and `numbers.Integral` stay out of annotations: `int` and `float` reach them only
  through runtime `register()`, which mypy ignores, so every call site fails. `float` already
  accepts `int`; `SupportsFloat` covers anything convertible. The `numbers` ABCs are for
  `isinstance`, below.

**At runtime — `isinstance` against the ABC, never `hasattr` or `type()`:**

- `isinstance(value, Mapping)` — never `isinstance(value, dict)` (breaks `MappingProxyType`,
  `ChainMap`) and never `hasattr(value, "keys")`.
- The one-method ABCs — `Iterable`, `Callable`, `Hashable`, `Sized` — implement
  `__subclasshook__`, so any object with the right dunders passes, registered or not. `Mapping`
  and `Sequence` do not: a class passes them only by inheriting or by `register()`.
- `isinstance(value, str)` / `bytes` guards come **before** `Iterable` / `Sequence` checks — both
  are sequences.
- `isinstance(value, numbers.Real)` for a number of unknown provenance — `isinstance(value, (int,
  float))` rejects `Fraction` and NumPy scalars such as `int64`. `bool` is an `Integral` — guard it
  if that matters — and `Decimal` is no `Real` at all, only a `numbers.Number`. **The carve-out is
  a value you parsed yourself**: a JSON decoder produces `int` and `float` and nothing else, so
  naming those two is the complete set, and reaching for `numbers` there buys an import and no
  case.
- `os.PathLike` for "a path-like thing", then normalise with `Path(value)`.

**Implementing a container — subclass the ABC and implement only the abstract methods:**

- `MutableMapping` — implement `__getitem__`, `__setitem__`, `__delitem__`, `__iter__`, `__len__`;
  get `get`, `pop`, `setdefault`, `update`, `keys`, `items`, `values`, `__contains__`, `__eq__`.
- `Sequence` — implement `__getitem__`, `__len__`; get `__iter__`, `__contains__`, `__reversed__`,
  `index`, `count`. `Iterator` — implement `__next__`. `Set` — implement `__contains__`,
  `__iter__`, `__len__`; get all set algebra.
- **Never subclass `dict`, `list`, `set` to customise behaviour** — their C-level methods bypass
  your overrides (`dict.update` does not call `__setitem__`). Subclass `collections.UserDict` /
  `UserList` / `UserString`, or the ABC.
- `NotImplementedError` in an ABC method is a bug: `@abstractmethod` so instantiation fails early.

```python
# WRONG — a dict subclass: update(), setdefault() and the constructor never call __setitem__,
# so `{"Content-Type": ...}` passed in stays mixed-case and the lowercased lookup misses it
@final
class CaseInsensitiveDict(dict[str, str]):
    @override
    def __getitem__(self, key: str) -> str:
        return super().__getitem__(key.lower())

    @override
    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key.lower(), value)

# CORRECT — every mixin method of MutableMapping goes through the five you implement
@final
class CaseInsensitiveDict(MutableMapping[str, str]):
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    @override
    def __getitem__(self, key: str) -> str:
        return self._store[key.lower()]

    @override
    def __setitem__(self, key: str, value: str) -> None:
        self._store[key.lower()] = value

    @override
    def __delitem__(self, key: str) -> None:
        del self._store[key.lower()]

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._store)

    @override
    def __len__(self) -> int:
        return len(self._store)
```

Beyond `collections.abc`: `numbers`, `io`, `os.PathLike`, `contextlib.AbstractContextManager`.
Write a contract of your own **only** when no stdlib ABC names the capability.
