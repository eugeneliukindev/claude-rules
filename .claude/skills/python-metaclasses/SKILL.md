---
name: python-metaclasses
description: >-
  Python class-creation hooks: metaclasses and their methods — __prepare__, __new__, __init__,
  __call__ — __init_subclass__ with keyword arguments in the class statement, __set_name__ on
  descriptors, __class_getitem__ and class decorators; the order they run in, which rung to take
  first, cooperative super() calls, validating a subclass at import, subclass registries and their
  import side effects, metaclass conflicts, and typing them with ClassVar and dataclass_transform.
  Use when writing or reviewing a metaclass, __init_subclass__, a descriptor, a plugin or subclass
  registry, a declarative base class, or a class statement with keyword arguments.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Class-Creation Hooks

Code that runs when a `class` statement executes runs at import, once per class, before any test
or request reaches it. Five mechanisms reach that moment, and they differ in how much they can do
and in how hard they are to find afterwards. `__init_subclass__` and `__set_name__` (PEP 487,
Python 3.6) exist because most metaclasses in the wild only wanted to customise their subclasses or
name their descriptors. The examples assume a 3.12 floor — PEP 695 generics, `typing.override`;
`typing.dataclass_transform` needs 3.11 or `typing_extensions`.

**In a one-off script none of this pays**: call the function. A script that grows a registry or a
declarative base has stopped being one (`python-scripts`).

## The Ladder: Take the Lowest Rung That Does the Job

| Rung | Reaches | Cannot |
|---|---|---|
| a function the composition root calls | anything, in plain sight | run by itself — which is the point |
| class decorator | one class that opts in; may return a new class (`slots=True`) | reach subclasses: they are not decorated |
| `__init_subclass__` on a base | every subclass, with typed keywords from the class statement | run for the base itself, replace the class, see the body while it executes |
| `__set_name__` on a descriptor | its owner class and the attribute name it was assigned to | anything beyond its own attribute |
| metaclass | the namespace before the body runs (`__prepare__`), operators on the class object (`for x in Cls`, `Cls[key]`, `len(Cls)`, `isinstance` checks), `Cls(...)` itself (`__call__`) | share a class with another metaclass that is not its ancestor or descendant |

Each rung up runs more implicitly. A metaclass costs the most: a hierarchy has one metaclass slot,
the metaclass runs for the base class too, and mypy checks nothing a metaclass receives from the
class statement. **A metaclass is earned only by the right-hand column of its own row** — the
namespace, an operator on the class, or instance creation. Everything else is a rung below.

```python
# WRONG — a metaclass for what __init_subclass__ does: it runs for Exporter too, so format_name
# needs a default, a subclass that forgets it gets "" silently, and format_name=3 passes mypy
class _ExporterMeta(ABCMeta):
    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        *,
        format_name: str = "",
    ) -> "_ExporterMeta":
        cls = super().__new__(mcls, name, bases, namespace)
        cls.format_name = format_name
        return cls


class Exporter(metaclass=_ExporterMeta):
    format_name: ClassVar[str]

    @abstractmethod
    def export(self, orders: Sequence[Order]) -> bytes: ...


# CORRECT — the hook runs for subclasses only, so the keyword is required and mypy checks it
class Exporter(ABC):
    format_name: ClassVar[str]

    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.format_name = format_name

    @abstractmethod
    def export(self, orders: Sequence[Order]) -> bytes: ...


@final
class JsonExporter(Exporter, format_name="json"):
    @override
    def export(self, orders: Sequence[Order]) -> bytes:
        return json.dumps([order.order_id for order in orders]).encode("utf-8")
```

## The Order They Run In

Observed on CPython 3.12 to 3.14 with every hook printing, for
`@decorate class Child(Base, flavour="x")` where `Base` has a metaclass and `Child` a descriptor:

1. `Meta.__prepare__("Child", bases, flavour="x")` returns the mapping the body will fill.
2. The class body executes into that mapping.
3. `Meta.__new__(mcls, "Child", bases, namespace, flavour="x")` calls `type.__new__`, which,
   before it returns:
   1. calls `__set_name__(Child, "field")` on every value in the namespace that defines it;
   2. calls `__init_subclass__(flavour="x")` — the nearest one in the MRO of `Child`, never the
      hook a class defines for itself.
4. `Meta.__init__(cls, "Child", bases, namespace, flavour="x")`.
5. The class decorators, innermost first.
6. Later, `Child(...)` goes through `Meta.__call__`, which runs the instance's `__new__` and
   `__init__`.

What follows from it:

- **`__init_subclass__` sees descriptors already named**, so it is where they are collected.
- **It runs inside `type.__new__`**, before the rest of a metaclass's `__new__` and before its
  `__init__`. Under `ABCMeta`, `cls.__abstractmethods__` does not exist yet;
  `inspect.isabstract(cls)` works there, because it scans for exactly this case.
- **It runs before the class decorators**: on a `@dataclass` subclass, `dataclasses.fields(cls)` is
  not available yet. And a hook cannot apply `dataclass(slots=True)` itself: that builds a new
  class, which re-enters the hook and fails with `already specifies __slots__`. A hook that must
  replace the class is a decorator's job.
- **A descriptor attached after the class exists** — `setattr(Cls, "x", Column(int))` — never gets
  `__set_name__`.
- **Class keywords travel to every metaclass method, then to `__init_subclass__`.** Every keyword
  but `metaclass=` reaches `__prepare__`, `__new__` and `__init__`; `type.__new__` passes what it
  is given to `__init_subclass__`, and `object.__init_subclass__` takes none, so a keyword nobody
  consumed fails with `TypeError: X.__init_subclass__() takes no keyword arguments`. `type.__init__`
  ignores keywords. A metaclass that consumes one leaves it out of `super().__new__(...)`.

## `__init_subclass__`

**An implicit classmethod**: no decorator, `cls` is the new subclass. Its parameters are the class
statement's keywords — keyword-only, typed, each a decision the subclass author makes in the line
that defines the class.

**It takes `**kwargs: object` and passes them to `super().__init_subclass__`.** The hooks of a
class with several bases are a chain through the MRO, and each link forwards what it did not
consume. A hook that swallows them breaks the chain silently: the next base's hook never runs, and
its keyword is accepted and thrown away.

```python
# WRONG — takes **kwargs and ends the chain: with class CsvExporter(Exporter, Audited,
# format_name="csv", audit_category="reports"), Audited's hook never runs and no error says so
class Exporter(ABC):
    format_name: ClassVar[str]

    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        cls.format_name = format_name

# CORRECT — what it does not consume goes on to the next hook, and object's rejects the leftovers
class Exporter(ABC):
    format_name: ClassVar[str]

    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.format_name = format_name
```

A hook with no `**kwargs` at all fails loudly instead — `unexpected keyword argument` — but still
ends the chain for every base after it. Forward even when nothing is expected to follow.

**Required or optional is a decision about every subclass, abstract ones included.** A required
keyword is demanded of an intermediate base too — `class _TabularExporter(Exporter)` without
`format_name` is a `TypeError`. When intermediates exist, make the keyword optional and require it
of concrete classes only, with `inspect.isabstract(cls)` in the hook; the price is that mypy no
longer reports the omission, the import does.

**Validate at definition time, not at first use.** A rule about the subclass — a value in range,
a combination that makes no sense, a method that must be overridden together with another — is
checked in the hook, so the import fails in every test run instead of the first production job of
that kind failing hours after a deploy.

```python
# WRONG — a subclass that forgets queue_name, or sets max_attempts = 0, imports cleanly and is
# found by the first job of its kind
class Job(ABC):
    queue_name: ClassVar[str]
    max_attempts: ClassVar[int] = _DEFAULT_MAX_ATTEMPTS

    @abstractmethod
    def run(self) -> None: ...

# CORRECT — the omission is a mypy error, the bad value an import error naming the class
class Job(ABC):
    queue_name: ClassVar[str]
    max_attempts: ClassVar[int]

    def __init_subclass__(
        cls, *, queue_name: str, max_attempts: int = _DEFAULT_MAX_ATTEMPTS, **kwargs: object
    ) -> None:
        super().__init_subclass__(**kwargs)
        if max_attempts < 1:
            raise JobError(f"{cls.__qualname__}: max_attempts is {max_attempts}, must be 1 or more")
        cls.queue_name = queue_name
        cls.max_attempts = max_attempts

    @abstractmethod
    def run(self) -> None: ...


@final
class SendReceipt(Job, queue_name="receipts", max_attempts=5):
    @override
    def run(self) -> None: ...
```

**The error names the offending class**, by `cls.__qualname__`, and is the package's own exception
(`errors.md`). The interpreter's own messages do not: a missing required keyword reads
`Job.__init_subclass__() missing 1 required keyword-only argument: 'queue_name'` — the base, not
the subclass; only the traceback's last frame points at the class statement.

**A hook is pure on the class it receives**: it reads the class and assigns to it. No I/O, no
settings, no logging configuration — it runs at import, and `modules.md` allows nothing executable
there beyond constants and the logger.

## Registries of Subclasses

The tempting use of the hook is a registry: every subclass files itself under its keyword, and a
lookup by name finds it. **The set of implementations a process has is decided by the composition
root, not by which modules happened to be imported.** A registry filled as a side effect of import
has three faults, each found late:

- **An implementation nobody imported is not registered.** `exporter_for("csv")` works in the test
  that imported `csv.py` and fails in the worker that did not; adding an import "to register it" is
  an unused import the linter wants removed.
- **A duplicate key overwrites quietly**, or raises at import with no say over which one wins.
- **Tests leak registrations.** A fake subclass defined in one test stays in the module-level
  registry for every test after it — shadowing the real one, or colliding with the next fake.

```python
# WRONG — the registry fills as modules are imported, so "csv" exists only after csv.py was
_EXPORTER_BY_FORMAT: Final[dict[str, type[Exporter]]] = {}


class Exporter(ABC):
    format_name: ClassVar[str]

    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.format_name = format_name
        _EXPORTER_BY_FORMAT[format_name] = cls

# CORRECT — the hook only names the class; the root lists the exporters this process has
class Exporter(ABC):
    format_name: ClassVar[str]

    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.format_name = format_name


def index_by_format(exporters: Iterable[Exporter]) -> dict[str, Exporter]:
    exporter_by_format: dict[str, Exporter] = {}
    for exporter in exporters:
        claimed = exporter_by_format.setdefault(exporter.format_name, exporter)
        if claimed is not exporter:
            raise ExportError(
                f"Format {exporter.format_name!r} is claimed by both "
                f"{type(claimed).__qualname__} and {type(exporter).__qualname__}"
            )
    return exporter_by_format

# in main(): index_by_format([CsvExporter(), JsonExporter()])
```

Where the implementations live, and that they are built in one place, is `python-contracts` and
`python-wiring`; a test builds its own index from fakes, and nothing leaks.

**The carve-out is an open set the root cannot name** — plugins shipped in other distributions,
which `python-packaging` lets register themselves. Then the loading is still one explicit call in
the root — entry points, or the package importing each built-in implementation in one place — a
duplicate raises naming both classes, and the registry is an object the root builds and a test can
replace, not a module global the hook writes to.

## Descriptors and `__set_name__`

A descriptor that needs its own attribute name — a column, a form field, a lazily parsed setting —
gets it from `__set_name__`, so the name is written once, on the left of the `=`. Together with
`__init_subclass__`, which runs after every descriptor is named, it builds a declarative base
without a metaclass:

```python
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
class OrderRow(CsvRow):
    order_id = Column(int)
    total_cents = Column(int)
```

`OrderRow(cells).order_id` is an `int` to mypy, through the overloaded `__get__`; accessed on the
class it is the `Column` itself. `cls.columns` read before the assignment is the parent's, so a
subclass of a row schema inherits its columns in order. The quotes around `CsvRow` are for the
3.12 floor; from 3.14 annotations are evaluated lazily and the forward reference needs none.

## Metaclasses

A metaclass is the class of a class: its methods run when a class is built, and its other dunders
are operators on the class object. Set with `metaclass=` on the base; subclasses inherit it.

- **`__prepare__(cls, name, bases, /, **kwargs) -> MutableMapping[str, object]`** — a classmethod,
  so ruff's `N804` wants `cls` here; called first, it returns the mapping the body executes into.
  The only hook that sees the body while it runs: an assignment repeated, the order of everything,
  values before they are overwritten.
- **`__new__(mcls, name, bases, namespace, **kwargs)`** builds the class through `super().__new__`
  and returns it — `mcls` is the metaclass, `cls` the class it returns;
  **`__init__(cls, name, bases, namespace, **kwargs)`** finishes it. Prefer `__init__` for anything
  that does not replace the namespace or the bases.
- **`__call__(cls, *args, **kwargs)`** is `Cls(...)`: it runs the instance's `__new__` and
  `__init__`, and can return anything — which is how a metaclass singleton is built, and a
  singleton is a global (`python-wiring`).
- **Operator dunders on the metaclass act on the class**: `__iter__`, `__len__`, `__getitem__`,
  `__contains__` make `for member in Cls` work — `Enum` is the stdlib's example, and a set of named
  values is an `Enum`, not a new metaclass. `__instancecheck__` and `__subclasscheck__` are how
  `ABCMeta` and runtime-checkable protocols answer `isinstance`; `__subclasshook__` on an ABC is
  the rung below.

**A class has exactly one metaclass, and it must be a (non-strict) subclass of the metaclass of
every base** — otherwise `TypeError: metaclass conflict`. `ABCMeta`, `EnumType`, a validation
library's model base and an ORM's declarative base each take the slot: a base with its own
metaclass cannot be mixed with any of them, and the only fix is a metaclass deriving from the
other one, which ties the code to that library's internals. In a library this is a cost every user
pays — one ORM ships a second declarative base with no metaclass for exactly those users. How a
contract avoids `ABCMeta` when the slot is taken is in `python-contracts`.

**A legitimate one: `__prepare__` refusing a repeated column.** By the time `__init_subclass__`
runs, a name assigned twice is one entry, and the first column is gone without a trace. Only the
namespace sees the second assignment:

```python
class _ColumnNamespace(dict[str, object]):
    @override
    def __setitem__(self, name: str, value: object) -> None:
        if name in self and isinstance(value, Column):
            raise CsvSchemaError(f"{self['__qualname__']}: column {name!r} is defined twice")
        super().__setitem__(name, value)


class _CsvRowMeta(type):
    @classmethod
    @override
    def __prepare__(
        cls, name: str, bases: tuple[type, ...], /, **kwargs: Any
    ) -> MutableMapping[str, object]:
        return _ColumnNamespace()


class CsvRow(metaclass=_CsvRowMeta): ...   # the rest as above
```

It refuses only columns, so a property and its `@x.setter` — the same name assigned twice by
design — still work. In your own repository ruff's `PIE794` reports a repeated class attribute
without any of this; the metaclass earns its slot when the classes are written by the users of a
library, whose linters you do not run. `Any` stays where `type.__prepare__`'s signature puts it.

## Typing

- **mypy checks class keywords against `__init_subclass__`**: a missing required one is
  `[call-arg]` on the class statement, a wrong type `[arg-type]`. A keyword the hook does not name
  passes through `**kwargs` unchecked and fails at import. **Keywords a metaclass consumes are not
  checked at all** — missing, misspelt or mistyped, mypy says nothing.
- **Declare on the base what the hook assigns**, as `ClassVar[...]`: undeclared,
  `cls.format_name = ...` is `"type[Exporter]" has no attribute "format_name"`. An attribute a
  metaclass adds is declared the same way, or as an annotation in the metaclass body — an
  instance attribute of the metaclass is a class attribute of its classes. What is not declared
  does not exist for the checker, and every use of it is an error or an `Any`.
- **A hook that synthesizes `__init__` is marked `@typing.dataclass_transform`** — on the base
  class, the metaclass or the decorator that does it — or mypy rejects every constructor call:
  `Unexpected keyword argument "order_id"`. Prefer the rung below, `@dataclass(frozen=True,
  slots=True, kw_only=True)` written on each class (`types.md`): explicit, and the only way to get
  `slots`, which a hook cannot add.

  ```python
  # CORRECT — mypy synthesizes the same frozen, keyword-only __init__ the hook builds at runtime
  @dataclass_transform(frozen_default=True, kw_only_default=True)
  class DomainEvent:
      def __init_subclass__(cls, **kwargs: object) -> None:
          super().__init_subclass__(**kwargs)
          dataclass(frozen=True, kw_only=True)(cls)


  @final
  class OrderPlaced(DomainEvent):
      order_id: int
      total_cents: int
  ```
- **A registry of classes is typed `type[Exporter]`**, and mypy refuses the abstract base itself
  there (`[type-abstract]`); a classmethod constructor on the base returns `Self`, so each subclass
  gets its own type back.
- **`__class_getitem__` is what makes `Cls[int]` work at runtime**, and a PEP 695 class
  (`class Repository[T]`) gets it without being written. Written by hand on a non-generic class it
  gives a runtime subscription mypy rejects — `"Gen" expects no type arguments` — and it is never a
  lookup: `Exporter["csv"]` is a registry with operator syntax, found by nobody who searches for a
  call.
