# Typing Hooks and Registries

### What a hook assigns is declared on the base as a `ClassVar`

**Why:** undeclared, `cls.game = ...` is `"type[ScoringRule]" has no attribute "game"`, and every
later read is an error or an `Any`. mypy checks class keywords against `__init_subclass__` — a
missing one is `[call-arg]` on the class statement, a wrong type `[arg-type]` — but a keyword the
hook does not name passes through `**kwargs` unchecked, and keywords a metaclass consumes are not
checked at all. An attribute a metaclass adds is declared the same way.

### A hook that synthesizes `__init__` is marked `@dataclass_transform`

**Why:** without it mypy rejects every constructor call — `Unexpected keyword argument "square"`.
The rung below is usually better: `@dataclass(frozen=True, slots=True, kw_only=True)` written on
each class is explicit, and the only way to get `slots`, which a hook cannot add (`run-order.md`).

**Example:**
```python
# WRONG — the hook builds __init__ at runtime, and mypy knows nothing about it
class GameEvent:
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(frozen=True, kw_only=True)(cls)


# CORRECT — mypy synthesizes the same frozen, keyword-only __init__ the hook builds
@dataclass_transform(frozen_default=True, kw_only_default=True)
class GameEvent:
    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        dataclass(frozen=True, kw_only=True)(cls)


@final
class PieceCaptured(GameEvent):
    piece: str
    square: str
```

### A registry of classes is typed `type[Base]`, and `Cls[...]` is for generics only

**Why:** mypy refuses the abstract base itself in a `type[ScoringRule]` slot (`[type-abstract]`);
a classmethod constructor on the base returns `Self`. A PEP 695 class gets `__class_getitem__`
without writing it; written by hand for a lookup, `ScoringRule["go"]` is a registry with operator
syntax, rejected by mypy and found by nobody who searches for a call.
