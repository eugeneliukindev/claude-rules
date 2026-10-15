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

How a contract is declared and what its methods look like are in `SKILL.md`.

### A contract is named after the capability, an implementation for what makes it concrete, and neither for its mechanism

**Why:** `TranslationEngine`, `TranslatorDirectory`, `Comparable` — an agent noun or an "-able"
adjective says what the thing does; `…Protocol`, `…Interface` and `…ABC` say how it was declared,
which no caller cares about, and `DefaultTranslationEngine` or `TranslationEngineImpl` says
nothing. The implementations carry the qualifier that distinguishes them — the driver, the
transport or the storage: `DeepLTranslationEngine`, `LdapTranslatorDirectory`. If nothing
distinguishes an implementation, there was no contract worth writing. Stdlib ABCs keep their
stdlib names.

**Example:**
```python
# WRONG — the mechanism as the name, and Base on a class that hands nothing down
class TranslatorDirectoryProtocol(Protocol):
    def find(self, email: str) -> Translator | None: ...

class BaseTranslatorDirectory(ABC):
    @abstractmethod
    def find(self, email: str) -> Translator | None: ...

# CORRECT — the contract names the capability; the implementation names what makes it concrete
class TranslatorDirectory(ABC):
    @abstractmethod
    def find(self, email: str) -> Translator | None: ...

@final
class LdapTranslatorDirectory(TranslatorDirectory):
    def __init__(self, *, connection: LdapConnection) -> None:
        self._connection = connection

    @override
    def find(self, email: str) -> Translator | None:
        entry = self._connection.search_one(f"(mail={email})")
        if entry is None:
            return None
        return Translator(translator_id=TranslatorId(entry.uid), email=email)
```

### `Base` means "inherit me", never "implement me"

**Why:** the prefix is earned by a class that carries shared *implementation* down — fields,
defaults, ready methods — as `BaseHTTPRequestHandler` and `BaseException` do; a contract hands
nothing down. The test is mechanical: delete the base and see what the subclasses lose — fields or
working methods make it a `Base`, only a promise the checker was already making makes it a
contract. A shared base only its own module inherits is private: `_BaseCookie`.

## Layout

How a contract is declared and what its methods look like are in `SKILL.md`.

### A contract and its implementations are one directory, nothing else is, and no contract means no directory

**Why:** the contract is the reason the implementations exist; one directory per capability, the
contract in `base.py`, one module per implementation named for what makes it concrete, and an
`__init__.py` exporting the contract and the implementations — so a new implementation is a new
file and no existing file changes. An implementation that will only ever be the only one is a
single module named concretely, with no `base.py` above it; the group appears when the second
implementation does, or when a test needs a fake — the same threshold that earns the contract.
**Except:** an implementation whose driver is an optional extra is reached through its builder, so
importing the contract never imports the driver (the extras reason for a function-level import,
`modules.md`).

### `base.py` is a position, not a `Base` class

**Why:** the module sits at the base of the group; the class inside it is still named for the
capability — `TranslationEngine`, never `BaseTranslationEngine`. One rule is about a file, the other
about a class.

### The contract's module imports nothing any implementation needs

**Why:** an import of a driver in `base.py` silently makes every consumer of the contract depend on
that driver, and the split stops paying.

**Example:**
```python
# WRONG — machine_translation/base.py imports the SDK one implementation uses
from deepl import DeepLClient

class TranslationEngine(ABC):
    @abstractmethod
    def translate(self, text: str, *, into: LanguageCode) -> str: ...

# CORRECT — machine_translation/deepl_engine.py is the only file that knows the SDK exists
from deepl import DeepLClient

from machine_translation.base import TranslationEngine

@final
class DeepLTranslationEngine(TranslationEngine):
    def __init__(self, *, client: DeepLClient, formality: str = DEFAULT_FORMALITY) -> None:
        self._client = client
        self._formality = formality

    @override
    def translate(self, text: str, *, into: LanguageCode) -> str:
        result = self._client.translate_text(text, target_lang=into, formality=self._formality)
        return str(result)
```

### A helper only one implementation uses is private and stays in the group

**Why:** `_glossary_upload.py` beside `deepl_engine.py` is found by whoever edits `deepl_engine.py`;
the same code in a shared `utils` is found by nobody and imported by everybody.

## Fakes

That a contract a unit test depends on has an in-memory fake in `tests/fakes.py`, inheriting the
contract, is in `testing.md`; this is the suite the fake and the real implementations pass.

### One parametrized fixture runs the contract suite against every implementation

**Why:** the tests are written once against the contract; the real implementations carry the
integration marker, so the unit run still takes the fake. A fake not held to the same tests drifts,
and the unit tests then prove the fake.

**Example:**
```python
# WRONG — the fake is tested by nothing, and the real glossary by its own separate tests
def test_in_memory_glossary_lists_added_term() -> None:
    glossary = InMemoryGlossary()
    entry = make_glossary_entry(language=LanguageCode("de"))
    glossary.add(entry)
    assert glossary.terms_in(LanguageCode("de")) == [entry]

# CORRECT — one suite, every implementation
@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("sql", id="sql", marks=pytest.mark.integration),
    ]
)
def glossary(request: pytest.FixtureRequest) -> Glossary:
    implementation: Glossary = request.getfixturevalue(f"{request.param}_glossary")
    return implementation

def test_added_term_is_listed_in_its_language(glossary: Glossary) -> None:
    entry = make_glossary_entry(language=LanguageCode("de"))

    glossary.add(entry)

    assert glossary.terms_in(LanguageCode("de")) == [entry]
```

