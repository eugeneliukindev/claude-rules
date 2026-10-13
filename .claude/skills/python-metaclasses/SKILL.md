---
name: python-metaclasses
description: >-
  Designs class-creation hooks: the rung to take — class decorator, __init_subclass__,
  __set_name__, metaclass — their order, subclass validation, registries, conflicts, typing. Use
  when writing a metaclass, __init_subclass__, a descriptor, a subclass or plugin registry, a
  declarative base, or a class statement with keyword arguments.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Class-Creation Hooks

Code that runs when a `class` statement executes runs at import, once per class, before any test
or request reaches it. `__init_subclass__` and `__set_name__` (PEP 487) exist because most
metaclasses in the wild only wanted to customise their subclasses or name their descriptors. The
examples assume a 3.12 floor. In a one-off script none of this pays: call the function
(`python-scripts`).

## The Ladder

| Rung | Reaches | Cannot |
|---|---|---|
| a function the composition root calls | anything, in plain sight | run by itself — which is the point |
| class decorator | one class that opts in; may return a new class (`slots=True`) | reach subclasses: they are not decorated |
| `__init_subclass__` on a base | every subclass, with typed keywords from the class statement | run for the base itself, replace the class, see the body while it executes |
| `__set_name__` on a descriptor | its owner class and the attribute name it was assigned to | anything beyond its own attribute |
| metaclass | the namespace before the body runs (`__prepare__`), operators on the class object (`for x in Cls`, `Cls[key]`, `len(Cls)`, `isinstance` checks), `Cls(...)` itself (`__call__`) | share a class with another metaclass that is not its ancestor or descendant |

### Take the lowest rung that does the job; a metaclass is earned only by its own column

**Why:** each rung up runs more implicitly. A hierarchy has one metaclass slot, the metaclass runs
for the base class too, and mypy checks nothing a metaclass receives from the class statement — so
a metaclass is for the namespace, an operator on the class or instance creation, and everything
else is a rung below.

**Example:**
```python
# WRONG — a metaclass for what __init_subclass__ does: it runs for Exporter too, so format_name
# needs a default, a subclass that forgets it gets "" silently, and format_name=3 passes mypy
class _ExporterMeta(ABCMeta):
    format_name: str

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
    @abstractmethod
    def export(self, reports: Sequence[Report]) -> bytes: ...


# CORRECT — the hook runs for subclasses only, so the keyword is required and mypy checks it
class Exporter(ABC):
    format_name: ClassVar[str]

    @override
    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.format_name = format_name

    @abstractmethod
    def export(self, reports: Sequence[Report]) -> bytes: ...


@final
class JsonExporter(Exporter, format_name="json"):
    @override
    def export(self, reports: Sequence[Report]) -> bytes:
        return json.dumps([report.title for report in reports]).encode("utf-8")
```

## `__init_subclass__`

An implicit classmethod: `@classmethod` is never written, `cls` is the new subclass, and it
overrides `object.__init_subclass__`, so it carries `@override`. Its parameters are the class
statement's keywords — keyword-only, typed, each a decision the subclass author makes in the line
that defines the class.

### The hook passes what it did not consume to `super().__init_subclass__`

**Why:** the hooks of a class with several bases are a chain through the MRO, and each link
forwards what it did not consume. A hook that swallows `**kwargs` breaks the chain silently: the
next base's hook never runs, and its keyword is accepted and thrown away. A hook with no `**kwargs`
fails loudly instead, and still ends the chain for every base after it.

**Example:**
```python
# WRONG — with class CsvExporter(Exporter, Audited, format_name="csv", audit_category="reports"),
# Audited's hook never runs and no error says so
class Exporter(ABC):
    format_name: ClassVar[str]

    @override
    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        cls.format_name = format_name


# CORRECT — the rest goes on to the next hook, and object's rejects any leftover
class Exporter(ABC):
    format_name: ClassVar[str]

    @override
    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.format_name = format_name
```

### A keyword required of every subclass is required of abstract intermediates too

**Why:** `class _TabularExporter(Exporter)` without `format_name` is a `TypeError` at import, though
it exports nothing. When intermediates exist, the keyword is optional and required of concrete
classes only, checked with `inspect.isabstract(cls)`; the price is that mypy no longer reports the
omission — the import does.

**Example:**
```python
# WRONG — the required keyword makes an abstract intermediate impossible to define
class Exporter(ABC):
    format_name: ClassVar[str]

    @override
    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.format_name = format_name


class _TabularExporter(Exporter):  # TypeError: missing 'format_name'
    @abstractmethod
    def columns(self) -> Sequence[str]: ...


# CORRECT — optional for abstract classes, demanded of every concrete one
class Exporter(ABC):
    format_name: ClassVar[str]

    @override
    def __init_subclass__(cls, *, format_name: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if format_name is not None:
            cls.format_name = format_name
        elif not inspect.isabstract(cls):
            raise ExportError(f"{cls.__qualname__}: a concrete exporter needs format_name")


class _TabularExporter(Exporter):
    @abstractmethod
    def columns(self) -> Sequence[str]: ...
```

### A rule about the subclass is checked in the hook, and the error names the class

**Why:** checked at definition, a value out of range fails the import in every test run instead of
the first production job of that kind, hours after a deploy. The error is the package's own
exception naming `cls.__qualname__` (`errors.md`); the interpreter's own message for a missing
keyword names the base. The hook is pure on the class it receives — no I/O, no settings, nothing
`modules.md` forbids at import. A type argument is not in `cls.__bases__`: for
`class IntRepository(Repository[int])` the hook reads `types.get_original_bases(cls)` (3.12).

**Example:**
```python
# WRONG — a subclass that forgets queue_name, or sets max_attempts = 0, imports cleanly
class Job(ABC):
    queue_name: ClassVar[str]
    max_attempts: ClassVar[int] = _DEFAULT_MAX_ATTEMPTS

    @abstractmethod
    def run(self) -> None: ...


# CORRECT — the omission is a mypy error, the bad value an import error naming the class
class Job(ABC):
    queue_name: ClassVar[str]
    max_attempts: ClassVar[int]

    @override
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

## Registries of Subclasses

### The composition root decides which implementations exist, not the imports that ran

**Why:** a registry the hook fills at import has three faults, each found late. An implementation
nobody imported is not registered — `exporter_for("csv")` works in the test that imported `csv.py`
and fails in the worker that did not, and an import added "to register it" is one the linter wants
removed. A duplicate key overwrites quietly. A fake subclass defined in one test stays registered
for every test after it. Where implementations live and where they are built is `python-contracts`
and `python-wiring`.
**Except:** an open set the root cannot name — plugins shipped in other distributions
(`python-packaging`). The loading is still one explicit call in the root, a duplicate raises naming
both classes, and the registry is an object a test can replace, not a global the hook writes to.

**Example:**
```python
# WRONG — "csv" exists only after csv.py was imported, by whoever happened to import it
class Exporter(ABC):
    format_name: ClassVar[str]

    @override
    def __init_subclass__(cls, *, format_name: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.format_name = format_name
        _EXPORTER_BY_FORMAT[format_name] = cls


_EXPORTER_BY_FORMAT: Final[dict[str, type[Exporter]]] = {}


# CORRECT — the hook only names the class; main() passes [CsvExporter(), JsonExporter()]
def index_by_format(exporters: Iterable[Exporter]) -> dict[str, Exporter]:
    exporter_by_format: dict[str, Exporter] = {}
    for exporter in exporters:
        claimed = exporter_by_format.setdefault(exporter.format_name, exporter)
        if claimed is not exporter:
            raise ExportError(
                f"format {exporter.format_name!r} is claimed by both "
                f"{type(claimed).__qualname__} and {type(exporter).__qualname__}"
            )
    return exporter_by_format
```

## Typing

### What a hook assigns is declared on the base as a `ClassVar`

**Why:** undeclared, `cls.format_name = ...` is `"type[Exporter]" has no attribute
"format_name"`, and every later read is an error or an `Any`. mypy checks class keywords against
`__init_subclass__` — a missing one is `[call-arg]` on the class statement, a wrong type
`[arg-type]` — but a keyword the hook does not name passes through `**kwargs` unchecked, and
keywords a metaclass consumes are not checked at all. An attribute a metaclass adds is declared the
same way.

### A hook that synthesizes `__init__` is marked `@dataclass_transform`

**Why:** without it mypy rejects every constructor call — `Unexpected keyword argument "user_id"`.
The rung below is usually better: `@dataclass(frozen=True, slots=True, kw_only=True)` written on
each class is explicit, and the only way to get `slots`, which a hook cannot add (`run-order.md`).

**Example:**
```python
# WRONG — the hook builds __init__ at runtime, and mypy knows nothing about it
class AuditEvent:
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(frozen=True, kw_only=True)(cls)


# CORRECT — mypy synthesizes the same frozen, keyword-only __init__ the hook builds
@dataclass_transform(frozen_default=True, kw_only_default=True)
class AuditEvent:
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(frozen=True, kw_only=True)(cls)


@final
class UserSuspended(AuditEvent):
    user_id: int
    reason: str
```

### A registry of classes is typed `type[Base]`, and `Cls[...]` is for generics only

**Why:** mypy refuses the abstract base itself in a `type[Exporter]` slot (`[type-abstract]`), and a
classmethod constructor on the base returns `Self`, so each subclass gets its own type back.
`__class_getitem__` is what makes `Cls[int]` work at runtime, and a PEP 695 class gets it without
writing it; written by hand for a lookup, `Exporter["csv"]` is a registry with operator syntax,
rejected by mypy and found by nobody who searches for a call.

## Run Order

**Before writing a hook that reads the class's abstract methods or dataclass fields, replaces the
class, or consumes a class keyword in a metaclass, read [run-order.md](run-order.md)** — the
sequence for one class statement, `inspect.isabstract` inside the hook, what only a decorator can
do, `abc.update_abstractmethods`, keywords a metaclass consumes.

## Descriptors

**Before writing a descriptor, `__set_name__`, `__get__`, or a declarative base whose class body
declares fields, read [descriptors.md](descriptors.md)** — the name from `__set_name__`, a
declarative base without a metaclass, errors that name the owner, caching on a slotted class.

## Metaclasses

**Before writing or reviewing a metaclass, or mixing a base that brings one, read
[metaclasses.md](metaclasses.md)** — what each metaclass method is for, `__init__` over `__new__`,
no singleton or value set through a metaclass, metaclass conflicts, a legitimate `__prepare__`.
