# Choosing a `collections.abc` ABC

## Contents

- Annotations: the most abstract parameter type that works, the most concrete return
- Runtime checks: `isinstance` against the ABC, `numbers` for a number of unknown origin
- Implementing a container: subclass the ABC
- Beyond `collections.abc`

The standard library already names "things you can iterate, index, call, hash". Those names go in
annotations, in runtime checks instead of `hasattr`, and instead of hand-rolled protocols.

## Annotations

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

Import them from `collections.abc`; the `typing` aliases are deprecated. A return is concrete —
`-> list[User]` — unless it deliberately hides the container: `-> Iterator[Row]` for a generator,
`-> Mapping[...]` for a read-only view. Attributes and dataclass fields follow the same rule:
`items: Sequence[Item]` when read-only, `list[Item]` only when the class itself mutates it.

### `Sequence[str]` also accepts a bare `str`, so a function that means "several" guards it

**Why:** a `str` is a `Sequence[str]` to the checker, and a single tag passed where a list of tags
was meant iterates as characters — `"urgent"` becomes six one-letter tags.

**Example:**
```python
# WRONG — label_issue(issue, "urgent") type-checks and adds six labels
def label_issue(issue: Issue, labels: Sequence[str]) -> Issue:
    return replace(issue, labels=(*issue.labels, *labels))


# CORRECT — a bare string is refused where several were meant
def label_issue(issue: Issue, labels: Sequence[str]) -> Issue:
    if isinstance(labels, str):
        raise TypeError("labels must be a sequence of strings, not one string")
    return replace(issue, labels=(*issue.labels, *labels))
```

### `numbers.Real` and `numbers.Integral` stay out of annotations

**Why:** `int` and `float` reach them only through a runtime `register()`, which mypy ignores, so
every call site with a plain number fails the check. `float` already accepts `int`;
`SupportsFloat` covers anything convertible. The `numbers` ABCs are for `isinstance` (below).

## Runtime Checks

### A runtime check asks the ABC, never `hasattr` or a concrete type

**Why:** `isinstance(value, dict)` refuses a `MappingProxyType` or a `ChainMap`, and
`hasattr(value, "keys")` accepts anything with that one attribute. The one-method ABCs —
`Iterable`, `Callable`, `Hashable`, `Sized` — implement `__subclasshook__`, so any object with the
dunder passes; `Mapping` and `Sequence` pass only what inherits or is registered. A `str` or `bytes`
guard comes before an `Iterable` or `Sequence` check, since both are sequences; `os.PathLike` names
"a path-like thing", normalised with `Path(value)`.

**Example:**
```python
# WRONG — a read-only MappingProxyType of headers is treated as a list of pairs
def normalise_headers(headers: object) -> dict[str, str]:
    if isinstance(headers, dict):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    if isinstance(headers, Iterable):
        return {str(key).lower(): str(value) for key, value in headers}
    raise TypeError(f"headers must be a mapping or pairs, not {type(headers).__name__}")


# CORRECT — any mapping passes as a mapping
def normalise_headers(headers: object) -> dict[str, str]:
    if isinstance(headers, Mapping):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    if isinstance(headers, Iterable):
        return {str(key).lower(): str(value) for key, value in headers}
    raise TypeError(f"headers must be a mapping or pairs, not {type(headers).__name__}")
```

### A number from elsewhere is checked against `numbers.Real`; one you parsed, `int` and `float`

**Why:** `isinstance(value, (int, float))` refuses a `Fraction` and a NumPy `int64`. `bool` is an
`Integral` — guard it if that matters — and `Decimal` is no `Real`, only a `numbers.Number`. A JSON
decoder produces `int` and `float` and nothing else, so for a value you parsed yourself those two
are the complete set, and `numbers` buys an import and no case.

## Implementing a Container

### A container subclasses its ABC and implements only the abstract methods — never `dict` or `list`

**Why:** the C-level methods of `dict`, `list` and `set` bypass your overrides — `dict.update`, the
constructor and `setdefault` never call `__setitem__`. The ABC routes every mixin method through
the ones you implement: `MutableMapping` needs `__getitem__`, `__setitem__`, `__delitem__`,
`__iter__` and `__len__` and gives `get`, `pop`, `setdefault`, `update`, `keys`, `items`, `values`,
`__contains__` and `__eq__`; `Sequence` needs `__getitem__` and `__len__`; `Set` needs
`__contains__`, `__iter__` and `__len__` and gives the set algebra. `collections.UserDict` is the
other way out.
**Except:** a metaclass `__prepare__` namespace — the class body stores every name with
`STORE_NAME`, which does call an overridden `__setitem__`, so a `dict` subclass is correct there
(`python-metaclasses`).

**Example:**
```python
# WRONG — update() and the constructor skip __setitem__, so a mixed-case key passed in stays
# mixed-case and the lowercased lookup misses it
@final
class CaseInsensitiveDict(dict[str, str]):
    @override
    def __getitem__(self, key: str) -> str:
        return super().__getitem__(key.lower())

    @override
    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key.lower(), value)


# CORRECT — every mixin method of MutableMapping goes through the five implemented here
@final
class CaseInsensitiveDict(MutableMapping[str, str]):
    def __init__(self) -> None:
        self._value_by_key: dict[str, str] = {}

    @override
    def __getitem__(self, key: str) -> str:
        return self._value_by_key[key.lower()]

    @override
    def __setitem__(self, key: str, value: str) -> None:
        self._value_by_key[key.lower()] = value

    @override
    def __delitem__(self, key: str) -> None:
        del self._value_by_key[key.lower()]

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._value_by_key)

    @override
    def __len__(self) -> int:
        return len(self._value_by_key)
```

## Beyond `collections.abc`

`numbers`, `io`, `os.PathLike` and `contextlib.AbstractContextManager` name further capabilities. A
contract of your own is written **only** when no standard ABC names the capability.
