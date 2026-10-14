# The Order the Hooks Run In

## Contents

- The sequence for one class statement
- What `__init_subclass__` can see at its moment
- What only a class decorator can do
- A decorator that implements an abstract method
- A metaclass that consumes a class keyword

## The Sequence

Observed on CPython 3.12 to 3.14 with every hook printing, for
`@decorate class Child(Base, variant="x")` where `Base` has a metaclass and `Child` a descriptor:

1. `Meta.__prepare__("Child", bases, variant="x")` returns the mapping the body will fill.
2. The class body executes into that mapping.
3. `Meta.__new__(mcls, "Child", bases, namespace, variant="x")` calls `type.__new__`, which,
   before it returns:
   1. calls `__set_name__(Child, "field")` on every value in the namespace that defines it;
   2. calls `__init_subclass__(variant="x")` — the nearest one in the MRO of `Child`, never the
      hook a class defines for itself.
4. `Meta.__init__(cls, "Child", bases, namespace, variant="x")`.
5. The class decorators, innermost first.
6. Later, `Child(...)` goes through `Meta.__call__`, which runs the instance's `__new__` and
   `__init__`.

A descriptor attached after the class exists — `setattr(Cls, "x", RuleOption(int))` — never gets
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
class VictoryCondition(ABC):
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__abstractmethods__:
            _check_concrete_condition(cls)

    @abstractmethod
    def is_met(self, board: BoardState) -> bool: ...


# CORRECT — the scan that works before ABCMeta has finished
class VictoryCondition(ABC):
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not inspect.isabstract(cls):
            _check_concrete_condition(cls)

    @abstractmethod
    def is_met(self, board: BoardState) -> bool: ...
```

### A hook that must replace the class, or read its dataclass fields, is a class decorator

**Why:** `__init_subclass__` runs before the decorators, so on a `@dataclass` subclass
`dataclasses.fields(cls)` is not available yet. And it cannot apply `dataclass(slots=True)`
itself: that builds a new class, which re-enters the hook, and the second pass fails —
`TypeError: Cannot overwrite attribute __setattr__ in class PieceMoved` on CPython 3.14.

**Example:**
```python
# WRONG — the slotted class re-enters the hook, and the import fails
class MoveEvent:
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(frozen=True, slots=True, kw_only=True)(cls)


# CORRECT — each class states it, and the decorator returns the slotted class
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class PieceMoved:
    from_square: str
    to_square: str
```

### A class decorator that implements an abstract method calls `abc.update_abstractmethods`

**Why:** `ABCMeta` computed the abstract set in step 3, before the decorator ran; without the call
the class still refuses to instantiate, naming the method the decorator just supplied.

**Example:**
```python
# WRONG — "Can't instantiate abstract class ... without an implementation for 'is_met'"
def won_by_last_piece[T: type[VictoryCondition]](condition_class: T) -> T:
    condition_class.is_met = _has_one_piece_left  # type: ignore[method-assign]  # added by design
    return condition_class


# CORRECT — the abstract set is recomputed after the method is added
def won_by_last_piece[T: type[VictoryCondition]](condition_class: T) -> T:
    condition_class.is_met = _has_one_piece_left  # type: ignore[method-assign]  # added by design
    abc.update_abstractmethods(condition_class)
    return condition_class
```

### A metaclass that consumes a class keyword leaves it out of `super().__new__`

**Why:** every keyword but `metaclass=` reaches `__prepare__`, `__new__` and `__init__`;
`type.__new__` passes what it is given on to `__init_subclass__`, and `object.__init_subclass__`
takes none — a keyword nobody consumed fails with
`TypeError: X.__init_subclass__() takes no keyword arguments`. `type.__init__` ignores keywords.

**Example:**
```python
# WRONG — notation= is passed on, and object.__init_subclass__ rejects it
class _PieceMeta(type):
    def __new__(
        mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any
    ) -> "_PieceMeta":
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        cls.notation = kwargs.get("notation", name[0])
        return cls


# CORRECT — the metaclass takes its keyword and forwards only the rest
class _PieceMeta(type):
    notation: str

    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        *,
        notation: str | None = None,
        **kwargs: Any,
    ) -> "_PieceMeta":
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        cls.notation = notation if notation is not None else name[0]
        return cls
```
