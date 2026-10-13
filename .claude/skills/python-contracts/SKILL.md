---
name: python-contracts
description: >-
  Designs contracts past the defaults: Protocol against ABC, runtime checks, the shapes a contract
  method takes, where implementations and fakes live. Use when writing an abstract base class, a
  Protocol, a base class or mixin, a second implementation or a test fake, or deciding what a
  consumer depends on.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Contracts and Implementations

When a class is worth writing at all, and the defaults for a contract — an ABC that implementations
inherit, sized to its consumer, composition for reuse — are in `classes.md`; `@override` on every
implementation is in `types.md`. This is what comes after: when a `Protocol` fits instead, what a
contract's methods look like, and where implementations and fakes live.

## Declaring a Contract

### `Protocol` is for code you cannot make inherit, or a project that chose it once

**Why:** a third-party type, a duck-typed shape someone else's code produces, a callback signature —
none of them can inherit your class. A project may also choose structural typing throughout:
implementations import nothing from the contract and a fake needs no base, at the price above (the
missing method is reported where the object is passed), so it is chosen once for the whole project,
never contract by contract.
**Except:** a published extension point is not that case — a plugin written for your library can
inherit the ABC you ship; a web framework that published its plugin points as Protocols replaced
them with ABCs in its next major.

**Example:**
```python
# WRONG — a Protocol plugin point: a plugin that forgets render() is accepted, fails when called
class Renderer(Protocol):
    def render(self, document: Document) -> bytes: ...


# CORRECT — the plugin inherits the ABC, and a forgotten method fails at the plugin's own class
class Renderer(ABC):
    @abstractmethod
    def render(self, document: Document) -> bytes: ...


# CORRECT — a shape produced by code you do not control stays a Protocol
class SupportsRead(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...
```

### `@abstractmethod` alone gives the static guarantee; `ABC` adds the runtime one, and a metaclass

**Why:** mypy reports `Cannot instantiate abstract class` from the decorators alone; `ABCMeta` adds
the refusal at construction time, and costs a metaclass — a class that already has a library's
metaclass (an ORM model, a framework base) cannot also be an `ABC`. Compiled with mypyc an `ABC`
builds and keeps `ABCMeta`, but the runtime refusal is gone: measured on mypy 2.4, the abstract
class instantiated without the error the interpreted module raised.
**Except:** decide once per project and say which — `ABC` where no foreign metaclass is in play, a
plain base with `@abstractmethod` where one is; never both shapes in one tree.

**Example:**
```python
# WRONG — an ABC under a framework base that brings its own metaclass: metaclass conflict at import
class ExportPlugin(Plugin, ABC):
    @abstractmethod
    def export(self, report: Report) -> bytes: ...


# CORRECT — the metaclass slot is taken, so the plain base keeps the checker's guarantee only
class ExportPlugin(Plugin):
    @abstractmethod
    def export(self, report: Report) -> bytes: ...
```

### A stdlib ABC that already names the capability is used directly

**Why:** `Iterable`, `Mapping`, `Sized` are the contract; a `Protocol` restating one makes a reader
open it to learn it is a `for` loop, and every list, tuple and generator already fits the original.

### A class with no abstract method is not a contract

**Why:** an implementation that does not define the method is accepted by the checker and fails at
the first call, with `NotImplementedError` where a type error should have been.

## The Shapes a Contract Method Takes

### A method that yields asynchronously is declared with plain `def` returning `AsyncIterator`

**Why:** declared `async def`, it promises a coroutine that returns an iterator, and every
implementation written as an async generator fails the override check.

**Example:**
```python
# WRONG — async def promises a coroutine: the async-generator implementation is an [override] error
class MessageFeed(ABC):
    @abstractmethod
    async def follow(self, room: RoomId) -> AsyncIterator[ChatMessage]: ...


# CORRECT — plain def returning AsyncIterator; implementations write `async def … yield`
class MessageFeed(ABC):
    @abstractmethod
    def follow(self, room: RoomId) -> AsyncIterator[ChatMessage]: ...


@final
class InMemoryMessageFeed(MessageFeed):
    def __init__(self) -> None:
        self._queue_by_room: dict[RoomId, asyncio.Queue[ChatMessage]] = {}

    @override
    async def follow(self, room: RoomId) -> AsyncIterator[ChatMessage]:
        queue = self._queue_by_room.setdefault(room, asyncio.Queue())
        while True:
            yield await queue.get()
```

### An abstract property is `@property` above `@abstractmethod`

**Why:** the other order fails when the class is defined — `attribute '__isabstractmethod__' of
'property' objects is not writable`.

### A generic contract binds its parameter in each implementation

**Why:** `class Repository[T](ABC)` is one contract for every entity; an implementation that stays
generic by accident — `class PostgresRepository[T](Repository[T])` — promises to store anything and
can store nothing in particular.

**Example:**
```python
# WRONG — the implementation stays generic: the table and the row mapping cannot be written
@final
class PostgresRepository[T](Repository[T]):
    def __init__(self, *, connection: DatabaseConnection) -> None:
        self._connection = connection

    @override
    def get(self, key: str) -> T:
        raise NotImplementedError


# CORRECT — the parameter is bound, and the body knows its table
@final
class PostgresDocumentRepository(Repository[Document]):
    def __init__(self, *, connection: DatabaseConnection) -> None:
        self._connection = connection

    @override
    def get(self, key: str) -> Document:
        row = self._connection.fetch_one(_SELECT_DOCUMENT, key)
        return Document(document_id=DocumentId(row["id"]), page_count=row["page_count"])
```

### A template method — the base's skeleton calling abstract steps — is `@final`

**Why:** a subclass then fills in the steps and cannot replace the skeleton; mypy reports `Cannot
override final attribute`.

**Example:**
```python
# WRONG — a subclass can replace render() and skip the header every report must carry
class Report(ABC):
    def render(self) -> str:
        return f"{self.title()}\n{self.body()}"

    @abstractmethod
    def title(self) -> str: ...

    @abstractmethod
    def body(self) -> str: ...


# CORRECT — the skeleton is final; subclasses supply the steps only
class Report(ABC):
    @final
    def render(self) -> str:
        return f"{self.title()}\n{self.body()}"

    @abstractmethod
    def title(self) -> str: ...

    @abstractmethod
    def body(self) -> str: ...
```

## What a Consumer Depends On

### Code uses what the collaborator's contract declares, and never reaches past it

**Why:** the Law of Demeter, applied to collaborators — a service that calls
`notifier.smtp.send_message(...)` depends on the transport its notifier hides, cannot run against
the fake, and breaks when the transport changes. The parameter typed as the contract enforces it:
mypy answers the reach with `[attr-defined]`, so the leak always starts with an annotation naming
the implementation. **Except:** data — `document.owner.address.city` reads a frozen structure and
couples to nothing that behaves.

**Example:**
```python
# WRONG — typed as the implementation, so the service can reach the transport behind the notifier
def send_receipt(receipt: Receipt, *, notifier: SmtpNotifier) -> None:
    notifier.smtp.send_message(receipt.as_email())


# CORRECT — typed as the contract: the call it declares is the only one there is
def send_receipt(receipt: Receipt, *, notifier: Notifier) -> None:
    notifier.send(receipt.recipient, receipt.as_message())
```

## Naming

**Before naming a contract, a base class or an implementation, read [naming.md](naming.md)** —
the capability as the contract's name, `Base` only for a class that hands down implementation,
an implementation named for what makes it concrete.

## Layout

**Before creating the module or directory for a contract or a new implementation, or deciding where
a helper one implementation uses goes, read [layout.md](layout.md)** — one directory per
capability with the contract in `base.py`, a contract module that imports nothing an
implementation needs, a one-implementation helper kept private in the group, no directory without
a contract.

## Fakes

**Before writing a fake of a contract for a test, or the tests every implementation must pass, read
[fakes.md](fakes.md)** — the fake inherits the contract and lives with the tests, and one contract
suite runs against every implementation.
