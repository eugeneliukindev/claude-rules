---
name: python-contracts
description: >-
  Python contracts and their implementations: an ABC with @abstractmethod versus a Protocol,
  ABC versus a plain base class when a metaclass is taken, @override on every implementation,
  one directory per capability with the contract in base.py, where a helper used by one
  implementation lives, and where a test fake lives. Use when writing an abstract base class, a
  Protocol or a second implementation of something, adding a fake for a test, or deciding where
  the implementations of one capability go.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Contracts and Implementations

When a class is worth writing at all is in `classes.md`. This is what comes after: which mechanism
declares the contract, what it and its implementations are called, and where they live.

## A Contract Is a Base Class with `@abstractmethod`; `Protocol` Is for Code You Do Not Control

A `Protocol` describes a *shape*; a base class the implementations inherit declares a *contract*.
Inside an application every implementation is yours to write, so the contract is nameable and the
inheritance is free — and it buys two things structural typing cannot:

- **The failure arrives at the class, not at the call site.** An implementation that forgot a
  method is an error where it is defined; a `Protocol` says nothing until someone passes it
  somewhere, and the error surfaces at that one call site, possibly far away.
- **The inheritance is the documentation.** `class SlackNotifier(Notifier)` states the intent in
  the line that defines the class; structural conformance is invisible until you diff the methods
  by hand.

**`@abstractmethod` alone gets the static guarantee; `ABC` adds a runtime one, and a metaclass.**
The type checker reports `Cannot instantiate abstract class "X" with abstract attribute "y"` from
the decorators alone — inheriting `abc.ABC` is not what makes that work. What `ABCMeta` adds is the
refusal at construction time, and what it costs is a metaclass: it conflicts with Django's model
metaclass, with mypyc compilation, and with any other library that wants that slot.

- **Default to `ABC`** in an application that compiles nothing and inherits no foreign metaclass.
  The runtime refusal is free there, and it catches the implementation built through a path the
  checker does not see.
- **Drop to a plain base class with `@abstractmethod`** when a metaclass is already spoken for, or
  the code is compiled. Neither guarantee the checker gives is lost.
- **Decide once per project and say which**, rather than mixing both shapes in one tree.

Hooking the creation of subclasses itself — keywords in the class statement, a subclass registry,
a metaclass of your own — is `python-metaclasses`.

**`@override` on every implementation of an abstract method**, whichever base you chose: a method
renamed on the contract then becomes an error in every implementation instead of a silent orphan.

```python
# WRONG — a Protocol for our own contract: a forgotten send surfaces only where it is passed
class Notifier(Protocol):
    def send(self, recipient: UserId, message: Message) -> None: ...


@final
class SmtpNotifier:
    def __init__(self, client: SmtpClient) -> None:
        self._client = client

    def send(self, recipient: UserId, message: Message) -> None: ...


# CORRECT — inherited: mypy reports a forgotten send on SmtpNotifier's own class line
class Notifier(ABC):
    @abstractmethod
    def send(self, recipient: UserId, message: Message) -> None: ...


@final
class SmtpNotifier(Notifier):
    def __init__(self, client: SmtpClient) -> None:
        self._client = client

    @override
    def send(self, recipient: UserId, message: Message) -> None: ...
```

Use `Protocol` when you cannot make the other side inherit: a third-party type, a duck-typed shape
someone else's code produces, a callback signature. **A published extension point is not that case**
— a plugin written for your library can inherit, so it inherits an ABC you ship, named for the
capability like any contract, and a forgotten method fails at the plugin's own class. A web
framework that published its plugin points as Protocols replaced them with ABCs in its next major.

```python
# WRONG — a plugin that forgets export() is accepted, and fails the first time it is called
class Exporter(Protocol):
    def export(self, orders: Sequence[Order]) -> bytes: ...

# CORRECT — plugins inherit it, so the forgotten method fails where the plugin class is defined
class Exporter(ABC):
    @abstractmethod
    def export(self, orders: Sequence[Order]) -> bytes: ...
```

**A stdlib ABC already names the capability** — `Iterable`, `Mapping`, `Sized` — so it is used
directly, never wrapped in a `Protocol`:

```python
# WRONG — a Protocol restating Iterable: a reader opens OrderSource to learn it is a for loop
class OrderSource(Protocol):
    def __iter__(self) -> Iterator[Order]: ...


def total_revenue(orders: OrderSource) -> Money: ...


# CORRECT — the stdlib ABC is the contract, and every list, tuple and generator fits it
def total_revenue(orders: Iterable[Order]) -> Money: ...
```

**A class with no abstract methods is not a contract**, whatever it is called:

```python
# WRONG — no abstract method: an implementation without send is accepted and fails when called
class Notifier(ABC):
    def send(self, recipient: UserId, message: Message) -> None:
        raise NotImplementedError


# CORRECT — abstract: the checker refuses an implementation that does not define send
class Notifier(ABC):
    @abstractmethod
    def send(self, recipient: UserId, message: Message) -> None: ...
```

## Naming Contracts and Implementations

- **A contract is named after the capability, without a prefix.** A contract base class — or, at a
  foreign boundary, a `Protocol` — is an agent noun or an "-able" adjective and nothing more:
  `Notifier`, `UserRepository`, `Comparable`. Never a mechanism suffix (`…Protocol`, `…Interface`,
  `…ABC`). The implementations carry the qualifier: `EmailNotifier`, `PostgresUserRepository`.
  Stdlib ABCs keep their stdlib names, and are never wrapped just to rename them.
- **`Base` means "inherit me", never "implement me".** The prefix is earned by a class that carries
  shared *implementation* down to its subclasses: fields, defaults, ready methods — that is what it
  means everywhere in the ecosystem, from `pydantic.BaseModel` to `BaseHTTPRequestHandler`. A
  contract has nothing to hand down, so it has no `Base` to earn. The test is mechanical: delete
  the base and see what the subclasses lose. Lose fields or working methods — it is a `Base`. Lose
  only a promise the checker was already making — it is a contract, named for the capability.
- **A shared base that only its own module inherits is private**: `_BaseCookie`, `_BaseAuth`.
- **Where a contract and its single implementation would collide**, the implementation names what
  makes it concrete — its driver, its transport, its storage — never `Default` or `Impl`. If
  nothing distinguishes it, there was no contract worth writing.

```python
# WRONG — Base on a contract, and the mechanism as the name
class BaseUserDirectory(ABC): ...           # nothing to inherit: it hands down no implementation
class UserDirectoryProtocol(Protocol): ...  # the mechanism is not the name

# CORRECT — the contract names the capability, an implementation names what makes it concrete
class UserDirectory(ABC):
    @abstractmethod
    def find(self, email: str) -> User | None: ...

@final
class LdapUserDirectory(UserDirectory):
    @override
    def find(self, email: str) -> User | None: ...
```

## A Contract and Its Implementations Are One Directory

The contract is the reason the implementations exist, so they live together — and nothing else
does. One directory per capability, named for it; the contract in `base.py`; one module per
implementation, named for what makes it concrete; `__init__.py` exporting the contract and the
implementations and nothing more — except an implementation whose driver is an optional extra,
which is reached through its builder so that importing the contract never imports the driver (the
per-extra facade in `python-packaging`).

```
notifications/
    base.py         # Notifier(ABC) — the contract, and the errors it raises
    slack.py        # SlackNotifier(Notifier) — the only file that imports the Slack SDK
    smtp.py         # SmtpNotifier(Notifier) — imports the SMTP client
    _templates.py   # private to the group: the bodies smtp.py renders
    __init__.py     # the contract and the implementations, nothing else
```

- **`base.py` is a position, not a `Base` class.** The module sits at the base of the group; the
  class inside it is still named for the capability — `Notifier`, never `BaseNotifier`. The two
  rules do not collide: one is about a file, the other about a class.
- **The contract's module imports nothing any implementation needs.** That is what makes the split
  worth having: a new implementation is a new file, and no existing file changes. An import of a
  driver in `base.py` silently makes every consumer of the contract depend on that driver.
- **A helper only one implementation uses is private and stays in the group** — `_templates.py`
  beside `smtp.py`, never in a shared `utils`.
- **No contract, no directory.** An implementation that will only ever be the only one is a single
  module named concretely, with no `base.py` above it. The group appears when the second
  implementation does, or when a test needs a fake — the same threshold that earns the contract.
- **A test fake is an implementation, and it lives with the tests** — `tests/fakes.py`, inheriting
  the contract like any other implementation. The group is what ships.
- **Every implementation passes one contract suite — the fake included.** The tests are written
  once against the contract and run for each implementation through a parametrized fixture; the
  real ones carry the integration marker, so the unit run still takes the fake. A fake that is not
  held to the same tests drifts, and the unit tests then prove the fake.

```python
@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def order_repository(request: pytest.FixtureRequest) -> OrderRepository:
    repository: OrderRepository = request.getfixturevalue(f"{request.param}_order_repository")
    return repository


def test_saved_order_is_found_by_id(order_repository: OrderRepository) -> None:
    order = make_order()

    order_repository.save(order)

    assert order_repository.find(order.order_id) == order
```
