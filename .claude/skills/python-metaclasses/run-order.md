# The Order the Hooks Run In

## Contents

- The sequence for one class statement
- What `__init_subclass__` can see at its moment
- What only a class decorator can do
- A decorator that implements an abstract method
- A metaclass that consumes a class keyword

## The Sequence

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

A descriptor attached after the class exists — `setattr(Cls, "x", Column(int))` — never gets
`__set_name__`.

## What Follows

### `__init_subclass__` collects named descriptors, and asks `inspect.isabstract` about abstractness

**Why:** it runs inside `type.__new__`, after every descriptor is named and before the rest of a
metaclass's `__new__`. Under `ABCMeta` that is before the abstract set is computed:
`cls.__abstractmethods__` raises `AttributeError` there, while `inspect.isabstract(cls)` scans for
exactly this case and answers.

**Example:**
```python
# WRONG — AttributeError: __abstractmethods__, for every subclass
class Report(ABC):
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__abstractmethods__:
            _check_concrete_report(cls)

    @abstractmethod
    def render(self) -> bytes: ...


# CORRECT — the scan that works before ABCMeta has finished
class Report(ABC):
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not inspect.isabstract(cls):
            _check_concrete_report(cls)

    @abstractmethod
    def render(self) -> bytes: ...
```

### A hook that must replace the class, or read its dataclass fields, is a class decorator

**Why:** `__init_subclass__` runs before the decorators, so on a `@dataclass` subclass
`dataclasses.fields(cls)` is not available yet. And it cannot apply `dataclass(slots=True)`
itself: that builds a new class, which re-enters the hook, and the second pass fails —
`TypeError: Cannot overwrite attribute __setattr__ in class Paid` on CPython 3.14.

**Example:**
```python
# WRONG — the slotted class re-enters the hook, and the import fails
class LedgerEvent:
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(frozen=True, slots=True, kw_only=True)(cls)


# CORRECT — each class states it, and the decorator returns the slotted class
@dataclass(frozen=True, slots=True, kw_only=True)
class Paid:
    invoice_number: str
    amount: Decimal
```

### A class decorator that implements an abstract method calls `abc.update_abstractmethods`

**Why:** `ABCMeta` computed the abstract set in step 3, before the decorator ran; without the call
the class still refuses to instantiate, naming the method the decorator just supplied.

**Example:**
```python
# WRONG — "Can't instantiate abstract class ... without an implementation for 'render'"
def with_plain_text_render[T: type[Report]](report_class: T) -> T:
    report_class.render = _render_plain_text  # type: ignore[method-assign]  # added by design
    return report_class


# CORRECT — the abstract set is recomputed after the method is added
def with_plain_text_render[T: type[Report]](report_class: T) -> T:
    report_class.render = _render_plain_text  # type: ignore[method-assign]  # added by design
    abc.update_abstractmethods(report_class)
    return report_class
```

### A metaclass that consumes a class keyword leaves it out of `super().__new__`

**Why:** every keyword but `metaclass=` reaches `__prepare__`, `__new__` and `__init__`;
`type.__new__` passes what it is given on to `__init_subclass__`, and `object.__init_subclass__`
takes none — a keyword nobody consumed fails with
`TypeError: X.__init_subclass__() takes no keyword arguments`. `type.__init__` ignores keywords.

**Example:**
```python
# WRONG — table= is passed on, and object.__init_subclass__ rejects it
class _TableMeta(type):
    def __new__(
        mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any
    ) -> "_TableMeta":
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        cls.table_name = kwargs.get("table", name.lower())
        return cls


# CORRECT — the metaclass takes its keyword and forwards only the rest
class _TableMeta(type):
    table_name: str

    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        *,
        table: str | None = None,
        **kwargs: Any,
    ) -> "_TableMeta":
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        cls.table_name = table if table is not None else name.lower()
        return cls
```
