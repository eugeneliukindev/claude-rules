---
name: python-contracts
description: >-
  Designs contracts past the defaults: Protocol against ABC, runtime checks, the shapes a contract
  method takes, where implementations and fakes live. Use when writing an abstract base class, a
  Protocol, a base class or mixin, a second implementation or a test fake, or deciding what a
  consumer depends on. Not for a metaclass or __init_subclass__ (python-metaclasses).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Contracts and Implementations

That a class is written only when triggered, that it inherits a contract and reuses by composition,
are in `classes.md`; `@override` and `@final` on every implementation are in `types.md`. What comes
after: when a `Protocol` fits, what a contract's methods look like, what a consumer is handed, and
where implementations and fakes live.

## Declaring a Contract

### `Protocol` is for code you cannot make inherit, or a project that chose it once

**Why:** a third-party type, a duck-typed shape someone else's code produces, a callback signature —
none of them can inherit your class. A Protocol reports a missing method where the object is passed,
not where the class is written; a project may still choose structural typing throughout, so that
implementations import nothing from the contract, but it chooses once for the whole project, never
contract by contract.
**Except:** a published extension point is not that case — a plugin written for your library can
inherit the ABC you ship; a web framework that published its plugin points as Protocols replaced
them with ABCs in its next major.

**Example:**
```python
# WRONG — a Protocol plugin point: a check that forgets inspect() is accepted, fails when called
class QualityCheck(Protocol):
    def inspect(self, segment: Segment) -> list[QualityIssue]: ...


# CORRECT — the plugin inherits the ABC, and a forgotten method fails at the plugin's own class
class QualityCheck(ABC):
    @abstractmethod
    def inspect(self, segment: Segment) -> list[QualityIssue]: ...


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
# WRONG — an ABC under an editor base that brings its own metaclass: metaclass conflict at import
class FileFilter(EditorExtension, ABC):
    @abstractmethod
    def extract(self, source: bytes) -> list[Segment]: ...


# CORRECT — the metaclass slot is taken, so the plain base keeps the checker's guarantee only
class FileFilter(EditorExtension):
    @abstractmethod
    def extract(self, source: bytes) -> list[Segment]: ...
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
class EditFeed(ABC):
    @abstractmethod
    async def edits(self, project_id: TranslationProjectId) -> AsyncIterator[SegmentEdit]: ...


# CORRECT — plain def returning AsyncIterator; implementations write `async def … yield`
class EditFeed(ABC):
    @abstractmethod
    def edits(self, project_id: TranslationProjectId) -> AsyncIterator[SegmentEdit]: ...


@final
class InMemoryEditFeed(EditFeed):
    def __init__(self) -> None:
        self._queue_by_project: dict[TranslationProjectId, asyncio.Queue[SegmentEdit]] = {}

    @override
    async def edits(self, project_id: TranslationProjectId) -> AsyncIterator[SegmentEdit]:
        queue = self._queue_by_project.setdefault(project_id, asyncio.Queue())
        while True:
            yield await queue.get()
```

### An abstract property is `@property` above `@abstractmethod`

**Why:** the other order fails when the class is defined —
`attribute '__isabstractmethod__' of 'property' objects is not writable`.

### A generic contract binds its parameter in each implementation

**Why:** `class KeyedStore[T](ABC)` is one contract for every entity; an implementation that stays
generic by accident — `class SqlKeyedStore[T](KeyedStore[T])` — promises to store anything and can
store nothing in particular.

**Example:**
```python
# WRONG — the implementation stays generic: the table and the row mapping cannot be written
@final
class SqlKeyedStore[T](KeyedStore[T]):
    def __init__(self, *, connection: SqlConnection) -> None:
        self._connection = connection

    @override
    def get(self, key: str) -> T:
        raise NotImplementedError


# CORRECT — the parameter is bound, and the body knows its table
@final
class SqlGlossaryStore(KeyedStore[GlossaryEntry]):
    def __init__(self, *, connection: SqlConnection) -> None:
        self._connection = connection

    @override
    def get(self, key: str) -> GlossaryEntry:
        row = self._connection.fetch_one(_SELECT_GLOSSARY_ENTRY, key)
        return GlossaryEntry(term=row["term"], approved_translation=row["approved_translation"])
```

### A template method — the base's skeleton calling abstract steps — is `@final`

**Why:** a subclass then fills in the steps and cannot replace the skeleton; mypy reports
`Cannot override final attribute`.

**Example:**
```python
# WRONG — a subclass can replace render() and skip the header every export must carry
class GlossaryExport(ABC):
    def render(self) -> str:
        return f"{self.header()}\n{self.rows()}"

    @abstractmethod
    def header(self) -> str: ...

    @abstractmethod
    def rows(self) -> str: ...


# CORRECT — the skeleton is final; subclasses supply the steps only
class GlossaryExport(ABC):
    @final
    def render(self) -> str:
        return f"{self.header()}\n{self.rows()}"

    @abstractmethod
    def header(self) -> str: ...

    @abstractmethod
    def rows(self) -> str: ...
```

## What a Consumer Depends On

### Code uses what the collaborator's contract declares, and never reaches past it

**Why:** the Law of Demeter, applied to collaborators — a function that calls
`machine_translation.session.translate_text(...)` depends on the transport its engine hides, cannot
run against the fake, and breaks when the transport changes. The parameter typed as the contract
enforces it: mypy answers the reach with `[attr-defined]`, so the leak always starts with an
annotation naming the implementation.
**Except:** data — `segment.unit.project.source_language` reads a frozen structure and couples to
nothing that behaves.

**Example:**
```python
# WRONG — typed as the implementation, so the function reaches the session behind the engine
def pretranslate(segment: Segment, *, machine_translation: HttpTranslationEngine) -> str:
    return machine_translation.session.translate_text(
        segment.source_text, target=segment.target_language
    )


# CORRECT — typed as the contract: the call it declares is the only one there is
def pretranslate(segment: Segment, *, machine_translation: TranslationEngine) -> str:
    return machine_translation.translate(segment.source_text, into=segment.target_language)
```

### A subclass accepts at least what its parent accepts and returns nothing wider

**Why:** code written against the parent must work with the subclass; mypy's `[override]` checks the
types, and nothing checks the behaviour — no new precondition, no dropped promise, no new exception.

**Example:**
```python
class TranslationMemory(ABC):
    @abstractmethod
    def store(self, segment: Segment) -> StoredUnit: ...


# WRONG — narrows the parameter: a caller passing any Segment to a TranslationMemory fails here
@final
class SqlTranslationMemory(TranslationMemory):
    def __init__(self, *, units: UnitTable, memory_code: str) -> None:
        self._units = units
        self._memory_code = memory_code

    @override
    def store(self, segment: ReviewedSegment) -> StoredUnit:
        unit_id = self._units.insert(self._memory_code, segment.source_text, segment.target_text)
        return StoredUnit(unit_id=unit_id)


# CORRECT — accepts what the parent accepts, and promises something narrower back
@final
class SqlTranslationMemory(TranslationMemory):
    def __init__(self, *, units: UnitTable, memory_code: str) -> None:
        self._units = units
        self._memory_code = memory_code

    @override
    def store(self, segment: Segment) -> CountedUnit:
        unit_id = self._units.insert(self._memory_code, segment.source_text, segment.target_text)
        return CountedUnit(unit_id=unit_id, word_count=segment.word_count)
```

### A contract holds only what its consumer calls

**Why:** a consumer handed more depends on it — its fake must implement it, and a change to a method
it never calls reaches it anyway. One class may implement several contracts; the split is in what
the consumer is given, not in the storage.
**Except:** split when a consumer that needs a different set exists, not in advance — a glossary
every caller uses whole stays one contract.

**Example:**
```python
# WRONG — the term count receives the whole glossary, writes included
class Glossary(ABC):
    @abstractmethod
    def add(self, entry: GlossaryEntry) -> None: ...

    @abstractmethod
    def terms_in(self, language: LanguageCode) -> list[GlossaryEntry]: ...


def count_terms(language: LanguageCode, *, glossary: Glossary) -> TermCount:
    return TermCount(language=language, term_count=len(glossary.terms_in(language)))


# CORRECT — the term count depends on the one capability it uses
class GlossaryTerms(ABC):
    @abstractmethod
    def terms_in(self, language: LanguageCode) -> list[GlossaryEntry]: ...


def count_terms(language: LanguageCode, *, glossary: GlossaryTerms) -> TermCount:
    return TermCount(language=language, term_count=len(glossary.terms_in(language)))
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
[fakes.md](fakes.md)** — one parametrized suite runs against every implementation, the fake
included.
