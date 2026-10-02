---
name: python-contracts
description: >-
  Python contracts and their implementations: an ABC with @abstractmethod versus a Protocol,
  ABC versus a plain base class when a metaclass is taken, @override on every implementation,
  one directory per capability with the contract in base.py, where a helper used by one
  implementation lives, and where a test fake lives. Use when writing an abstract base class, a
  Protocol or a second implementation of something, adding a fake for a test, or deciding where
  the implementations of one capability go.
---

# Contracts and Implementations

Naming a contract and its implementations is in `naming.md`; when a class is worth writing at all
is in `classes.md`. This is what comes after: which mechanism declares the contract, and where its
implementations live.

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

**`@override` on every implementation of an abstract method**, whichever base you chose: a method
renamed on the contract then becomes an error in every implementation instead of a silent orphan.

```python
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
someone else's code produces, a callback signature. **A stdlib ABC already names the capability** —
`Iterable`, `Mapping`, `Sized` — so it is used directly, never wrapped in a `Protocol`. **A class
with no abstract methods is not a contract**, whatever it is called.

## A Contract and Its Implementations Are One Directory

The contract is the reason the implementations exist, so they live together — and nothing else
does. One directory per capability, named for it; the contract in `base.py`; one module per
implementation, named for what makes it concrete; `__init__.py` exporting the contract and the
implementations and nothing more — except an implementation whose driver is an optional extra,
which is reached through its builder so that importing the contract never imports the driver (the
per-extra façade in `python-packaging`).

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
