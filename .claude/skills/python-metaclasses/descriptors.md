# Descriptors and `__set_name__`

## Contents

- A descriptor learns its name from `__set_name__`
- A declarative base from `__set_name__` and `__init_subclass__`, without a metaclass
- An error in `__set_name__` names the owner
- A descriptor that caches into the instance on a slotted class

### A descriptor that needs its attribute name takes it from `__set_name__`

**Why:** a column, a form field or a rule option that is handed its own name repeats it —
`base_minutes = RuleOption("base_minutes", int)` — and the two drift apart on the first rename.
`__set_name__` receives the name on the left of the `=`, so it is written once.

**Example:**
```python
# WRONG — the key is written twice, and a rename of one side reads the wrong option
class RuleOption[T]:
    def __init__(self, key: str, parse: Callable[[str], T]) -> None:
        self.key = key
        self._parse = parse


# CORRECT — the attribute's own name is the key
class RuleOption[T]:
    key: str

    def __init__(self, parse: Callable[[str], T]) -> None:
        self._parse = parse

    def __set_name__(self, owner: type[object], name: str) -> None:
        self.key = name
```

### A declarative base is `__set_name__` plus `__init_subclass__`, without a metaclass

**Why:** `__init_subclass__` runs after every descriptor in the body has been named
(`run-order.md`), so it collects them; no metaclass slot is spent. An overloaded `__get__` makes
`options.base_minutes` an `int` to mypy and `ChessClockOptions.base_minutes` the `RuleOption`
itself. `cls.declared_options` read before the assignment is the parent's, so a subclass of an
options class inherits its options in order. The quotes around `RuleOptions` are for the 3.12
floor; from 3.14 annotations are evaluated lazily.

**Example:**
```python
# WRONG — a metaclass for what the two hooks below do
class _RuleOptionsMeta(type):
    def __init__(
        cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any
    ) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        cls.declared_options = tuple(
            value for value in namespace.values() if isinstance(value, RuleOption)
        )


# CORRECT — the descriptor names itself; the base collects the named options
class RuleOption[T]:
    key: str

    def __init__(self, parse: Callable[[str], T]) -> None:
        self._parse = parse

    def __set_name__(self, owner: type[object], name: str) -> None:
        self.key = name

    @overload
    def __get__(self, options: None, owner: type[object]) -> Self: ...
    @overload
    def __get__(self, options: "RuleOptions", owner: type[object]) -> T: ...
    def __get__(self, options: "RuleOptions | None", owner: type[object]) -> Self | T:
        if options is None:
            return self
        return self._parse(options.raw_value(self.key))


class RuleOptions:
    declared_options: ClassVar[tuple[RuleOption[object], ...]] = ()

    @override
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        own_options = tuple(value for value in vars(cls).values() if isinstance(value, RuleOption))
        cls.declared_options = (*cls.declared_options, *own_options)

    def __init__(self, raw_by_key: Mapping[str, str]) -> None:
        missing_keys = [
            option.key for option in self.declared_options if option.key not in raw_by_key
        ]
        if missing_keys:
            raise RuleOptionsError(f"{type(self).__qualname__}: missing options {missing_keys}")
        self._raw_by_key = dict(raw_by_key)

    def raw_value(self, key: str) -> str:
        return self._raw_by_key[key]


@final
class ChessClockOptions(RuleOptions):
    base_minutes = RuleOption(int)
    increment_seconds = RuleOption(int)
```

### An error raised in `__set_name__` is the package's own, naming the owner

**Why:** from 3.12 it reaches the import unwrapped — 3.11 wrapped it in `RuntimeError` — so the
message is what the author of the class statement reads, like a hook's.

### A descriptor that caches into the instance needs a `__dict__`, which `slots=True` removes

**Why:** `functools.cached_property` on a slotted dataclass imports cleanly and fails at first
access — `No '__dict__' attribute on 'DominoHand' instance to cache 'pip_total' property`. There it
is a plain `@property`, or a field the constructor computes.

**Example:**
```python
# WRONG — fails on the first read of pip_total
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class DominoHand:
    pips: tuple[int, ...]

    @cached_property
    def pip_total(self) -> int:
        return sum(self.pips)


# CORRECT — computed on each read; the class has no __dict__ to cache into
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class DominoHand:
    pips: tuple[int, ...]

    @property
    def pip_total(self) -> int:
        return sum(self.pips)
```
