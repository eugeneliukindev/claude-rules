---
name: python-metaclasses
description: >-
  Designs class-creation hooks: the rung to take — class decorator, __init_subclass__,
  __set_name__, metaclass — their order, subclass validation, registries, conflicts, typing. Use
  when writing a metaclass, __init_subclass__, a descriptor, a subclass or plugin registry, a
  declarative base, or a class statement with keyword arguments. Not for an ABC or Protocol
  (python-contracts).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Class-Creation Hooks

Code that runs when a `class` statement executes runs at import, once per class, before any test
or request reaches it. `__init_subclass__` and `__set_name__` (PEP 487) exist because most
metaclasses in the wild only wanted to customise their subclasses or name their descriptors. The
examples assume a 3.12 floor. An ABC or a `Protocol` is `python-contracts`, where implementations
are built is `python-wiring`, plugins found through entry points are `python-packaging`; in a
one-off script none of this pays — call the function (`python-scripts`).

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
# WRONG — a metaclass for what __init_subclass__ does: it runs for ScoringRule too, so game needs a
# default, a subclass that forgets it gets "" silently, and game=3 passes mypy
class _ScoringRuleMeta(ABCMeta):
    game: str

    def __new__(
        mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], *, game: str = ""
    ) -> "_ScoringRuleMeta":
        cls = super().__new__(mcls, name, bases, namespace)
        cls.game = game
        return cls


class ScoringRule(metaclass=_ScoringRuleMeta):
    @abstractmethod
    def score(self, board: BoardState) -> int: ...


# CORRECT — the hook runs for subclasses only, so the keyword is required and mypy checks it
class ScoringRule(ABC):
    game: ClassVar[str]

    @override
    def __init_subclass__(cls, *, game: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.game = game

    @abstractmethod
    def score(self, board: BoardState) -> int: ...


@final
class TerritoryScoring(ScoringRule, game="go"):
    @override
    def score(self, board: BoardState) -> int:
        return board.count_enclosed_points()
```

## `__init_subclass__`

An implicit classmethod: `@classmethod` is never written, `cls` is the new subclass, and it
carries `@override`. Its parameters are the class statement's keywords — keyword-only, typed, each
a decision the subclass author makes in the line that defines the class.

### The hook passes what it did not consume to `super().__init_subclass__`

**Why:** the hooks of a class with several bases are a chain through the MRO, and each link
forwards what it did not consume. A hook that swallows `**kwargs` breaks the chain silently: the
next base's hook never runs, and its keyword is accepted and thrown away. A hook with no `**kwargs`
fails loudly instead, and still ends the chain for every base after it.

**Example:**
```python
# WRONG — with class ChessScoring(ScoringRule, Versioned, game="chess", edition="2023"),
# Versioned's hook never runs and no error says so
class ScoringRule(ABC):
    game: ClassVar[str]

    @override
    def __init_subclass__(cls, *, game: str, **kwargs: object) -> None:
        cls.game = game


# CORRECT — the rest goes on to the next hook, and object's rejects any leftover
class ScoringRule(ABC):
    game: ClassVar[str]

    @override
    def __init_subclass__(cls, *, game: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.game = game
```

### A keyword required of every subclass is required of abstract intermediates too

**Why:** `class _CaptureScoring(ScoringRule)` without `game` is a `TypeError` at import, though it
scores nothing. When intermediates exist, the keyword is optional and required of concrete classes
only, checked with `inspect.isabstract(cls)`; the price is that mypy no longer reports the omission
— the import does.

**Example:**
```python
# WRONG — the required keyword makes an abstract intermediate impossible to define
class ScoringRule(ABC):
    game: ClassVar[str]

    @override
    def __init_subclass__(cls, *, game: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.game = game


class _CaptureScoring(ScoringRule):  # TypeError: missing 'game'
    @abstractmethod
    def piece_values(self) -> Mapping[str, int]: ...


# CORRECT — optional for abstract classes, demanded of every concrete one
class ScoringRule(ABC):
    game: ClassVar[str]

    @override
    def __init_subclass__(cls, *, game: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if game is not None:
            cls.game = game
        elif not inspect.isabstract(cls):
            raise RulePluginError(f"{cls.__qualname__}: a concrete scoring rule needs game")


class _CaptureScoring(ScoringRule):
    @abstractmethod
    def piece_values(self) -> Mapping[str, int]: ...
```

### A rule about the subclass is checked in the hook, and the error names the class

**Why:** checked at definition, a value out of range fails the import in every test run instead of
the first table that loads the plugin, hours after a deploy. The error is the package's own
exception naming `cls.__qualname__` (`errors.md`); the interpreter's own message for a missing
keyword names the base. The hook is pure on the class it receives — nothing `modules.md` forbids
at import. A type argument is not in `cls.__bases__`: for `class DiceTray(Tray[Die])` the
hook reads `types.get_original_bases(cls)` (3.12).

**Example:**
```python
# WRONG — a subclass that forgets game, or sets max_players = 1, imports cleanly
class SetupRule(ABC):
    game: ClassVar[str]
    max_players: ClassVar[int] = _DEFAULT_MAX_PLAYERS

    @abstractmethod
    def opening_board(self, player_count: int) -> BoardState: ...


# CORRECT — the omission is a mypy error, the bad value an import error naming the class
class SetupRule(ABC):
    game: ClassVar[str]
    max_players: ClassVar[int]

    @override
    def __init_subclass__(
        cls, *, game: str, max_players: int = _DEFAULT_MAX_PLAYERS, **kwargs: object
    ) -> None:
        super().__init_subclass__(**kwargs)
        if max_players < 2:
            raise RulePluginError(f"{cls.__qualname__}: max_players is {max_players}, must be 2+")
        cls.game = game
        cls.max_players = max_players

    @abstractmethod
    def opening_board(self, player_count: int) -> BoardState: ...


@final
class CheckersSetup(SetupRule, game="checkers", max_players=2):
    @override
    def opening_board(self, player_count: int) -> BoardState:
        return BoardState.checkers_opening()
```

## Registries of Subclasses

### The composition root decides which implementations exist, not the imports that ran

**Why:** a registry the hook fills at import has three faults, each found late. An implementation
nobody imported is not registered — `scoring_for("go")` works in the test that imported `go.py`
and fails in the server that did not, and an import added "to register it" is one the linter wants
removed. A duplicate key overwrites quietly. A fake subclass defined in one test stays registered
for every test after it.
**Except:** an open set the root cannot name — plugins shipped in other distributions. The loading
is still one explicit call in the root, a duplicate raises naming both classes, and the registry is
an object a test can replace, not a global the hook writes to.

**Example:**
```python
# WRONG — "go" exists only after go.py was imported, by whoever happened to import it
class ScoringRule(ABC):
    game: ClassVar[str]

    @override
    def __init_subclass__(cls, *, game: str, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.game = game
        _SCORING_BY_GAME[game] = cls


_SCORING_BY_GAME: Final[dict[str, type[ScoringRule]]] = {}


# CORRECT — the hook only names the class; main() passes [TerritoryScoring(), ChessScoring()]
def index_by_game(rules: Iterable[ScoringRule]) -> dict[str, ScoringRule]:
    rule_by_game: dict[str, ScoringRule] = {}
    for rule in rules:
        claimed = rule_by_game.setdefault(rule.game, rule)
        if claimed is not rule:
            raise RulePluginError(
                f"game {rule.game!r} is claimed by both "
                f"{type(claimed).__qualname__} and {type(rule).__qualname__}"
            )
    return rule_by_game
```

## Typing

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
