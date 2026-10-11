# Metaclasses

## Contents

- The metaclass methods and what each one is for
- One metaclass per class, and what that costs a library's users
- A legitimate one: `__prepare__` refusing a repeated column

A metaclass is the class of a class: its methods run when a class is built, and its other dunders
are operators on the class object. It is set with `metaclass=` on the base, and subclasses inherit
it. Which rung to take before this one is in `SKILL.md`.

## The Methods

- **`__prepare__(cls, name, bases, /, **kwargs) -> MutableMapping[str, object]`** — a classmethod,
  so ruff's `N804` wants `cls` here; called first, it returns the mapping the body executes into.
  The only hook that sees the body while it runs: an assignment repeated, the order of everything,
  values before they are overwritten.
- **`__new__(mcls, name, bases, namespace, **kwargs)`** builds the class through `super().__new__`
  and returns it — `mcls` is the metaclass, `cls` the class it returns.
- **`__init__(cls, name, bases, namespace, **kwargs)`** finishes it.
- **`__call__(cls, *args, **kwargs)`** is `Cls(...)`: it runs the instance's `__new__` and
  `__init__`, and can return anything.
- **Operator dunders on the metaclass act on the class**: `__iter__`, `__len__`, `__getitem__` and
  `__contains__` make `for member in Cls` work, and `__instancecheck__` and `__subclasscheck__` are
  how `ABCMeta` and runtime-checkable protocols answer `isinstance`.

### What does not replace the namespace or the bases goes in `__init__`, not `__new__`

**Why:** `__new__` exists to choose what the class is built from; work on a finished class in
`__new__` runs before `__init__` sees it and makes the override harder to cooperate with.

**Example:**
```python
# WRONG — __new__ overridden only to set an attribute on the finished class
class _RegisteredMeta(type):
    def __new__(
        mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any
    ) -> "_RegisteredMeta":
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        cls.registered_name = name.lower()
        return cls


# CORRECT — the class exists; __init__ finishes it
class _RegisteredMeta(type):
    registered_name: str

    def __init__(
        cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any
    ) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        cls.registered_name = name.lower()
```

### A singleton through `__call__`, or a set of named values through operators, is not a metaclass

**Why:** a metaclass `__call__` that returns one shared instance is a global with extra steps
(`python-wiring`); a set of named values iterated with `for member in Cls` is an `Enum` — the
stdlib's own example of operator dunders on a metaclass.

**Example:**
```python
# WRONG — Cls() returns one shared instance: a global no test can replace
class _SingletonMeta(type):
    _instance_by_class: ClassVar[dict[type, object]] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in _SingletonMeta._instance_by_class:
            _SingletonMeta._instance_by_class[cls] = super().__call__(*args, **kwargs)
        return _SingletonMeta._instance_by_class[cls]


class RateLimiter(metaclass=_SingletonMeta): ...


# CORRECT — the composition root builds one and passes it to everything that shares it
@final
class RateLimiter:
    def __init__(self, *, requests_per_second: float) -> None:
        self._requests_per_second = requests_per_second
```

## Conflicts

### A base that adds a metaclass cannot be mixed with any other metaclass

**Why:** a class has exactly one metaclass, and it must be a (non-strict) subclass of the
metaclass of every base — otherwise `TypeError: metaclass conflict`. `ABCMeta`, `EnumType`, a
validation library's model base and an ORM's declarative base each take the slot, and the only fix
is a metaclass deriving from the other one, tying the code to that library's internals. In a
library this is a cost every user pays — one ORM ships a second declarative base with no metaclass
for exactly those users. How a contract avoids `ABCMeta` when the slot is taken is in
`python-contracts`.

**Example:**
```python
# WRONG — an ABC whose metaclass is a plain type subclass: mixing it with ABC is a conflict
class _AuditedMeta(type):
    pass


class Audited(metaclass=_AuditedMeta): ...


class AuditedExporter(Audited, ABC): ...  # TypeError: metaclass conflict


# CORRECT — no metaclass at all; the hook mixes with anything
class Audited:
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)


class AuditedExporter(Audited, ABC): ...
```

## A Legitimate One

### `__prepare__` is how a library refuses a column defined twice

**Why:** by the time `__init_subclass__` runs, a name assigned twice is one entry, and the first
column is gone without a trace; only the namespace sees the second assignment. It refuses only
columns, so a property and its `@x.setter` still work. In your own repository ruff's `PIE794`
reports a repeated class attribute without any of this; the metaclass earns its slot when the
classes are written by the users of a library, whose linters you do not run. `Any` stays where
`type.__prepare__`'s signature puts it. The namespace is a `dict` subclass — the one place that is
correct, because the class body stores every name through `__setitem__`
([collections-abc.md](../python-types/collections-abc.md)).

**Example:**
```python
# WRONG — the second subscriber_id silently replaces the first
class SubscriberRow(CsvRow):
    subscriber_id = Column(int)
    email = Column(str)
    subscriber_id = Column(str)


# CORRECT — the namespace refuses the repeat while the body runs
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


class CsvRow(metaclass=_CsvRowMeta):
    columns: ClassVar[tuple[Column[object], ...]] = ()
```
