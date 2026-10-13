# Descriptors and `__set_name__`

## Contents

- A descriptor learns its name from `__set_name__`
- A declarative base from `__set_name__` and `__init_subclass__`, without a metaclass
- An error in `__set_name__` names the owner
- A descriptor that caches into the instance on a slotted class

### A descriptor that needs its attribute name takes it from `__set_name__`

**Why:** a column, a form field or a lazily parsed setting that is handed its own name repeats it
— `email = Column("email", str)` — and the two drift apart on the first rename. `__set_name__`
receives the name on the left of the `=`, so it is written once.

**Example:**
```python
# WRONG — the header is written twice, and a rename of one side reads the wrong column
class Column[T]:
    def __init__(self, header: str, parse: Callable[[str], T]) -> None:
        self.header = header
        self._parse = parse


# CORRECT — the attribute's own name is the header
class Column[T]:
    header: str

    def __init__(self, parse: Callable[[str], T]) -> None:
        self._parse = parse

    def __set_name__(self, owner: type[object], name: str) -> None:
        self.header = name
```

### A declarative base is `__set_name__` plus `__init_subclass__`, without a metaclass

**Why:** `__init_subclass__` runs after every descriptor in the body has been named
(`run-order.md`), so it collects them; no metaclass slot is spent. An overloaded `__get__` makes
`row.subscriber_id` an `int` to mypy and `RowClass.subscriber_id` the `Column` itself.
`cls.columns` read before the assignment is the parent's, so a subclass of a row schema inherits
its columns in order. The quotes around `CsvRow` are for the 3.12 floor; from 3.14 annotations are
evaluated lazily.

**Example:**
```python
# WRONG — a metaclass for what the two hooks below do
class _CsvRowMeta(type):
    def __init__(
        cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any
    ) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        cls.columns = tuple(value for value in namespace.values() if isinstance(value, Column))


# CORRECT — the descriptor names itself; the base collects the named columns
class Column[T]:
    header: str

    def __init__(self, parse: Callable[[str], T]) -> None:
        self._parse = parse

    def __set_name__(self, owner: type[object], name: str) -> None:
        self.header = name

    @overload
    def __get__(self, row: None, owner: type[object]) -> Self: ...
    @overload
    def __get__(self, row: "CsvRow", owner: type[object]) -> T: ...
    def __get__(self, row: "CsvRow | None", owner: type[object]) -> Self | T:
        if row is None:
            return self
        return self._parse(row.cell(self.header))


class CsvRow:
    columns: ClassVar[tuple[Column[object], ...]] = ()

    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        own_columns = tuple(value for value in vars(cls).values() if isinstance(value, Column))
        cls.columns = (*cls.columns, *own_columns)

    def __init__(self, cells: Mapping[str, str]) -> None:
        missing_headers = [column.header for column in self.columns if column.header not in cells]
        if missing_headers:
            raise CsvSchemaError(f"{type(self).__qualname__}: missing columns {missing_headers}")
        self._cells = dict(cells)

    def cell(self, header: str) -> str:
        return self._cells[header]


@final
class SubscriberRow(CsvRow):
    subscriber_id = Column(int)
    email = Column(str)
```

### An error raised in `__set_name__` is the package's own, naming the owner

**Why:** from 3.12 it reaches the import unwrapped — 3.11 wrapped it in `RuntimeError` — so the
message is what the author of the class statement reads, like a hook's.

### A descriptor that caches into the instance needs a `__dict__`, which `slots=True` removes

**Why:** `functools.cached_property` on a slotted dataclass imports cleanly and fails at first
access — `No '__dict__' attribute on 'Basket' instance to cache 'total' property`. There it is a
plain `@property`, or a field the constructor computes.

**Example:**
```python
# WRONG — fails on the first read of total
@dataclass(frozen=True, slots=True, kw_only=True)
class Basket:
    prices: tuple[Decimal, ...]

    @cached_property
    def total(self) -> Decimal:
        return sum(self.prices, start=Decimal(0))


# CORRECT — computed on each read; the class has no __dict__ to cache into
@dataclass(frozen=True, slots=True, kw_only=True)
class Basket:
    prices: tuple[Decimal, ...]

    @property
    def total(self) -> Decimal:
        return sum(self.prices, start=Decimal(0))
```
