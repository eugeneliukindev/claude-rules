---
paths:
  - "**/*.py"
---

# Python — Classes

Functions are the default; a class is an upgrade that must be triggered.

## When a Class Earns Its Place

### A class is written only when one of seven triggers holds

**Why:** a module is already a namespace with "methods"; a class without a trigger adds `self` and a
constructor to code that needed neither.

1. **State survives between calls** — a token bucket, a pool, an accumulator, an open session.
2. **Invariants tie values together** — `Money`, `DateRange`: a frozen dataclass with methods.
3. **The behaviour must be swappable** — two implementations behind one contract, or a test fake.
4. **Several operations share the same dependencies** — three or more functions taking the same two
   or more collaborators; repeated *values* forming one concept are a parameter object instead.
5. **There is a lifecycle** — acquire and release, `__enter__`/`__exit__`, `close()`.
6. **A framework demands it** — `Enum`, `Exception`, a dataclass.
7. **The composition root builds it with collaborators** — a service or an adapter that takes its
   dependencies and settings in its constructor, one public method or several.

**Example:**
```python
# WRONG — __init__ plus one method: the object holds nothing between calls
@final
class RecipeCalories:
    def __init__(self, recipe: Recipe) -> None:
        self._recipe = recipe

    def calculate(self) -> int:
        return sum(ingredient.calories for ingredient in self._recipe.ingredients)


# CORRECT — the same work as a function
def recipe_calories(recipe: Recipe) -> int:
    return sum(ingredient.calories for ingredient in recipe.ingredients)
```

### Shapes that mean the class should not exist

**Why:** each pays the cost of a class and gets nothing a class gives.

- `__init__` plus one method over values it was handed, with no collaborator to hold; only
  `@staticmethod`s; a box for constants; a stateless "service" with no dependencies.
- **Methods that group by who asks for their changes** — two actors in one class: split the class,
  never reorder it (below).

**Example:**
```python
# WRONG — a class used as a box: the name adds a level and holds no behaviour
class DocumentLimits:
    MAX_PAGES: Final = 500
    MAX_SIZE_BYTES: Final = 20_000_000


# CORRECT — module constants, each named for what it limits
MAX_DOCUMENT_PAGES: Final = 500
MAX_DOCUMENT_SIZE_BYTES: Final = 20_000_000
```

### Before a class, try a partial, a closure, an options dataclass or a split module

**Why:** each gives the one thing needed without a lifecycle; a long module of independent functions
is idiomatic Python and does not improve by growing a `self`. A collaborator the root wires in is
the seventh trigger, not this case.

**Example:**
```python
# WRONG — a class whose only job is to remember one value for a sort key
@final
class DistanceFrom:
    def __init__(self, origin: Coordinate) -> None:
        self._origin = origin

    def __call__(self, store: Store) -> float:
        return distance_km(self._origin, store.location)


def nearest_stores(stores: Iterable[Store], *, home: Coordinate) -> list[Store]:
    return sorted(stores, key=DistanceFrom(home))


# CORRECT — a closure remembers the value
def nearest_stores(stores: Iterable[Store], *, home: Coordinate) -> list[Store]:
    return sorted(stores, key=lambda store: distance_km(home, store.location))
```

## One Actor per Module and Class

### A module or a class answers to one actor — whoever asks for its changes

**Why:** code answering to two actors ships the fix one of them asks for to the other. This is SRP,
not "does one thing" (that rule is for functions), and the test is *who*, not *which layer*.
**Except:** knowledge both actors share — what counts as regular hours — lives once, on the data; if
they come to mean different things, those are two rules with two names.

**Example:**
```python
# WRONG — one module, two actors: a pay fix finance asks for ships with HR's hours report
def _regular_hours(timesheet: Timesheet) -> Decimal:
    return min(timesheet.hours_worked, REGULAR_WEEK_HOURS)


def calculate_pay(timesheet: Timesheet) -> Decimal:  # finance
    return _regular_hours(timesheet) * timesheet.hourly_rate


def report_hours(timesheet: Timesheet, *, working_days: int) -> HoursReport:  # HR
    regular = _regular_hours(timesheet)
    return HoursReport(regular=regular, total=timesheet.hours_worked, working_days=working_days)


# CORRECT — timesheet.py: the rule both actors share, on the data
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Timesheet:
    hours_worked: Decimal
    hourly_rate: Decimal

    @property
    def regular_hours(self) -> Decimal:
        return min(self.hours_worked, REGULAR_WEEK_HOURS)


# CORRECT — payroll.py, finance's module
def calculate_pay(timesheet: Timesheet) -> Decimal:
    return timesheet.regular_hours * timesheet.hourly_rate


# CORRECT — hours_report.py, HR's module
def report_hours(timesheet: Timesheet, *, working_days: int) -> HoursReport:
    regular = timesheet.regular_hours
    return HoursReport(regular=regular, total=timesheet.hours_worked, working_days=working_days)

```

## Inversion and Composition

### Collaborators arrive through the constructor, never built inside

**Why:** one built inside cannot be replaced in a test, and the signature hides what it needs.

**Example:**
```python
# WRONG — the repository is built inside: no test can hand in a fake
@final
class DocumentService:
    def __init__(self, pool: DatabasePool) -> None:
        self._documents = PostgresDocumentRepository(pool)

    def archive(self, document_id: DocumentId) -> None:
        self._documents.mark_archived(document_id)


# CORRECT — it arrives from the composition root
@final
class DocumentService:
    def __init__(self, *, documents: DocumentRepository) -> None:
        self._documents = documents

    def archive(self, document_id: DocumentId) -> None:
        self._documents.mark_archived(document_id)
```

### A class inherits only what it is; reuse is composition

**Why:** a class inherits a contract, or a `Base` whose fields and methods it *is* — an `Exception`
subclass is an exception. Behaviour wanted only for its methods — an HTTP call, a retry, a formatter
— arrives as a collaborator: a base class collecting helpers ties every subclass to all of them, and
no test can swap one out.
**Except:** a mixin adds behaviour over the class's own contract, holds no state and declares
`__slots__ = ()`.

**Example:**
```python
# WRONG — inherits a helper class for its HTTP call: every notifier is now an HTTP client
class _HttpHelpers:
    _transport: HttpTransport

    def _post_json(self, path: str, payload: Mapping[str, object]) -> None:
        self._transport.post(path, body=json.dumps(payload).encode(), timeout=_TIMEOUT_SECONDS)


@final
class SlackNotifier(Notifier, _HttpHelpers):
    def __init__(self, *, post_message_path: str = DEFAULT_POST_MESSAGE_PATH) -> None:
        self._post_message_path = post_message_path

    @override
    def send(self, recipient: UserId, message: Message) -> None:
        self._post_json(self._post_message_path, {"channel": recipient, "text": message})


# CORRECT — the client is a collaborator the notifier holds
@final
class SlackNotifier(Notifier):
    def __init__(
        self, *, client: JsonClient, post_message_path: str = DEFAULT_POST_MESSAGE_PATH
    ) -> None:
        self._client = client
        self._post_message_path = post_message_path

    @override
    def send(self, recipient: UserId, message: Message) -> None:
        self._client.post_json(self._post_message_path, {"channel": recipient, "text": message})
```

