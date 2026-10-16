---
name: python-contracts
description: >-
  Designs contracts past the defaults: Protocol against ABC, runtime checks, the shapes a contract
  method takes, what a consumer is handed, where implementations and fakes live. ALWAYS invoke this
  skill when a task adds a second implementation or store, an in-memory or fake one for tests, an
  abstract base class, a Protocol, a base class or mixin. Do not write a contract directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Contracts and Implementations

When a class is written, inheritance and composition are in `classes.md`; a subclass keeping its parent's promises and a contract holding only what its consumer calls, in `principles.md`; `@override` and `@final`, in `types.md`. This skill covers what comes after: when a `Protocol` fits, what a contract's methods look like, what a consumer is handed, and where implementations and fakes live.

## Declaring a Contract

- **Use a `Protocol` only for code you cannot make inherit, or in a project that chose structural typing once, for all its contracts.** A third-party type, a shape someone else's code produces or a callback signature cannot inherit your class, and a `Protocol` reports a missing method where the object is passed, not where the class is written; a published extension point, like a plugin for your library, inherits the ABC you ship.
- **Choose `ABC` or a plain base with `@abstractmethod` once per project, and never mix both in one tree.** `@abstractmethod` alone makes instantiating an abstract class a type error, and `ABC` adds the refusal at construction at the cost of a metaclass; a class that already has a library's metaclass, like an ORM model or a framework base, takes the plain base.
- **Use a stdlib ABC that already names the capability directly.** A `Protocol` restating `Iterable`, `Mapping` or `Sized` makes a reader open it to learn it is a `for` loop.
- **Give every contract an abstract method.** An implementation that skips a method of a class with none passes the checker and fails at the first call with `NotImplementedError`.

## The Shapes a Contract Method Takes

- **Declare a method that yields asynchronously with plain `def` returning `AsyncIterator`, and implement it as `async def` with `yield`.** Declared `async def`, it promises a coroutine that returns an iterator, and every async-generator implementation fails the override check.
- **Put `@property` above `@abstractmethod` on an abstract property.** The other order fails when the class is defined.
- **Bind a generic contract's type parameter in each implementation.** An implementation that stays generic by accident promises to store anything and can store nothing in particular.
- **Make a template method, the base's skeleton calling abstract steps, `@final`.** A subclass then fills in the steps and cannot replace the skeleton.

## What a Consumer Depends On

- **Use only what the collaborator's contract declares, and never reach past it.** A call through the engine to the transport it hides cannot run against the fake and breaks when the transport changes; type the parameter as the contract, so the reach is a type error. Reading through frozen data couples to nothing that behaves, and is fine.

## Naming

- **Name a contract for its capability, an implementation for what makes it concrete, and neither for its mechanism.** An agent noun or an "-able" adjective says what the thing does; `...Protocol`, `...Interface` and `...ABC` say how it was declared, and `Default...` or `...Impl` say nothing. Give an implementation the qualifier that distinguishes it (driver, transport or storage), and keep stdlib ABC names.
- **Write no contract when nothing distinguishes its one implementation.**
- **Prefix a class `Base` only when it hands down implementation, never when it is a contract.** Delete the base and see what the subclasses lose: fields or working methods make it a `Base`, a promise the checker already made makes it a contract; a shared base only its own module inherits is private, like `_BaseCookie`.

## Layout

- **Put a contract and its implementations in one directory holding nothing else: the contract in `base.py`, one module per implementation, an `__init__.py` exporting both.** A new implementation is then a new file and no existing file changes.
- **Keep a lone implementation one concretely named module with no `base.py`.** The group appears with the second implementation or a test's fake; an implementation whose driver is an optional extra is reached through its builder, so importing the contract never imports the driver (`modules.md`).
- **Name the class in `base.py` for its capability, never `Base...`.** `base.py` names a position in the group, not a class.
- **Import nothing into the contract's module that an implementation needs.** A driver imported in `base.py` makes every consumer of the contract depend on it.
- **Keep a helper only one implementation uses private, inside the group.** Next to its implementation it is found by whoever edits it; in a shared `utils` it is found by nobody and imported by everybody.

## Fakes

- **Run one contract suite against every implementation through one parametrized fixture.** Write the tests once against the contract and mark the real implementations as integration, so the unit run still takes the fake; a fake not held to the same tests drifts, and the unit tests then prove the fake.
