---
name: python-packaging
description: >-
  The public surface of a Python package: the three levels of visibility, __all__ and the flat
  façade, _internal subpackages, lazy exports through TYPE_CHECKING plus __getattr__, stability
  tiers as directories, semantic-versioning and deprecation rules, and keeping an optional
  dependency inside the one implementation module that uses it. Use when building a Python package
  other code imports — a library, an SDK, a shared kernel — or when working with __init__.py,
  optional extras, a façade or a deprecation.
---

# Packaging and Public Surface

The underscore rule that applies to every module is in `core.md`; this file is about the surface a
package promises.

## The Three Levels of Visibility

| Level | How it is marked | Who may import it | What it guarantees |
|---|---|---|---|
| Public | listed in the package's `__init__.py` `__all__` | anyone | follows the deprecation rules |
| Package-internal | a module named `_name.py`, or an `_internal/` sub-package | only modules inside that package | may change in any release |
| Module-private | a name prefixed `_` inside a module | only that module | may change at any time |

**What the underscore actually does**: nothing at runtime except excluding the name from a star
import. Its value is entirely social and static — the linters flag imports of private names across
module boundaries. That is enough, provided the convention is followed consistently.

**When to encapsulate a whole module**

- **Always, for a package other code imports.** Consumers must read one file and see everything
  they may rely on.
- **Whenever a module exists only to serve its siblings** — prefix it with `_` so nobody outside
  grows a dependency on it.
- **Underscoring every module is not needed inside an application package** whose only consumer is
  itself, when layer boundaries are already enforced. There, contracts do the work and a prefix on
  two hundred modules is noise. This is a carve-out for the *module name* only: the `__init__.py`
  still declares the surface, because a layer contract enforces *direction* and says nothing about
  *which names* a neighbouring layer may use.

## Hiding a Whole Subsystem

- **Name the private area `_internal/`, with the underscore.** That is what `pydantic` and `pip`
  ship. `internal/` without it is a trap: NumPy shipped `numpy/core/` documented as private but
  named public, downstream imported from it for years, and undoing that took a dedicated NEP,
  compatibility stubs and a lint rule to fix other people's code. A docstring saying "this is
  private" is not a boundary; the name is.
- **Whether the underscore repeats inside is a project's choice, made once.** PEP 8 says it need
  not: *"An interface is also internal if any containing namespace is internal"* — and `pip`
  follows that, with plain `cli/`, `index/`, `models/` inside `_internal/`. `pydantic` does the
  opposite and prefixes all twenty-eight (`_fields.py`, `_repr.py`), so that a module read on its
  own, or grepped for, or seen in a traceback, still says what it is. Pick one and apply it to the
  whole area; the failure is a tree where half the modules carry the prefix and nobody can say
  which half is deliberate.
- **The private area's `__init__.py` is empty.** `pydantic/_internal/__init__.py` is zero bytes —
  internal code imports the module it needs directly. A façade declares a contract, and there is no
  contract to declare here.

## The Flat Public Façade

How the standard library, `pydantic` and `attrs` are built:

- Implementation lives in private modules: `_client.py`, `_models.py`, `_transport.py`.
- `__init__.py` imports the public names from them and lists exactly those in `__all__`.
- Consumers write one stable path regardless of which private module the name currently lives in.
  Deep paths are unsupported by construction.
- Internal code imports from the private modules directly — never through the package's own
  `__init__`, which would create a cycle and make module load order significant.

  ```python
  # acme_core/__init__.py — the whole public surface, and nothing else
  from ._identifiers import OrderId as OrderId, UserId as UserId
  from ._models import Order as Order, User as User
  from ._repository import UserRepository as UserRepository

  __all__ = ["Order", "OrderId", "User", "UserId", "UserRepository"]
  ```

**Rules**

- **`__all__` is written out as string literals** — never computed, never appended to
  conditionally. List or tuple is a project's choice; a tuple says "this does not change at
  runtime" and costs nothing.
- **Sort it, or group it — and the choice follows the length.** Up to a screenful, alphabetical:
  a reader checks membership by scanning. Past that, sorting scatters related names across a
  hundred lines, and grouping under topic comments (`# validators`, `# serializers`) is what a
  reader actually navigates. `pydantic` exports 151 names grouped under 21 comments, and keeps its
  lazy-import table in the same order so the two can be diffed by eye.
- **A name is either in `__all__` or private.** There is no third state: a public-looking name that
  is not exported is a promise nobody made and everybody will rely on.
- **NEVER import a private name across a package boundary.** If another package needs it, it is not
  private: promote it deliberately, with the deprecation guarantees that implies. Copying it is
  worse.
- **Deep paths that must stay importable** (plugin entry points) are an explicit, documented part
  of the public surface, not an accident.
- **`py.typed` ships with every typed package**, or consumers get `Any` for the whole API.
- **A test asserts that `__all__` matches the intended surface**, so an accidental export fails.

### What May Live in `__init__.py`

**In an application package: imports and `__all__`, nothing else.** Logic there runs on every
import of anything below it, and it runs in an order nobody chose.

**In a library façade the bar is different**, because the file is a contract rather than a
convenience, and three things earn their place:

- **A guard that fails fast on an incompatible environment.** `pydantic` checks its compiled core's
  version on the first line and deletes the helper afterwards — a mismatch there produces a clear
  error instead of an incomprehensible one three frames deep.
- **A deprecation shim**, so a moved or renamed name keeps working and says so.
- **Lazy exports through `__getattr__`** — the next section.

### Lazy Exports: `TYPE_CHECKING` Plus `__getattr__`

A façade that imports every submodule eagerly makes `import yourpackage` pay for the whole library,
including the parts this process will never touch. The fix is to import on first access, and the
objection — that a name arriving through `__getattr__` is invisible to the type checker — is
answered by declaring the imports a second time under `TYPE_CHECKING`:

  ```python
  # yourpackage/__init__.py
  if TYPE_CHECKING:
      # Everything is served lazily by __getattr__ below; these are what the type
      # checker and the IDE read.
      from .validators import AfterValidator, BeforeValidator

  _LAZY: Final = {
      # validators
      'AfterValidator': '.validators',
      'BeforeValidator': '.validators',
  }

  def __getattr__(name: str) -> object:
      module = import_module(_LAZY[name], __spec__.parent)
      ...
  ```

The checker reads the `TYPE_CHECKING` block and sees full signatures; the interpreter reads the
table and imports nothing until asked. **Both halves must list the same names**, so keep them in
the same order and in the same groups — the only real cost of the pattern is that they can drift,
and side-by-side ordering is what makes the drift visible in a diff.

Use it in a façade over many submodules, or where one export pulls a heavy optional dependency.
Do **not** use it to compute names, to export something that does not exist as a real attribute of
a real module, or in an application package, where the import cost was never the problem.

## The Stability Tier Is a Package

A promise that lives in a changelog is a promise the consumer reads once. A promise that lives in
the import path is one they re-read at every call site. Give each tier its own package, and
`from yourpkg.experimental.pipeline import Pipeline` states the terms in the line that depends on
them:

| path | what it promises |
|---|---|
| `yourpkg/` | the public surface, under the deprecation rules below |
| `yourpkg/experimental/` | may change or vanish in any release |
| `yourpkg/deprecated/` | still works, is going away, and says so on use |
| `yourpkg/v1/` | the previous major, shipped alongside for migration |
| `yourpkg/_internal/` | not yours |

- **The tier's `__init__.py` states the contract in one line.** `pydantic/experimental/__init__.py`
  is exactly that: *"contains potential new features that are subject to change."*
- **Moving between tiers is the release event**, and it is a move of a file, which a reviewer
  sees — not an edit to a table of promises somewhere else.
- **Do not invent tiers you do not need.** An application has one surface and needs none of this;
  a library usually needs `_internal/` and nothing more until the first thing it regrets shipping.

## Compatibility and Deprecation

`__all__` is the contract: anything not in it may change freely, anything in it follows the rules
below. Keep the surface as small as viable — every exported name is a promise.

- **Semantic versioning semantics**: breaking change → major; new capability → minor; fix → patch.
  "Breaking" includes removing or renaming an exported name, tightening accepted types, loosening
  returned types, changing defaults, reordering positional parameters, and raising a new exception
  type from an existing flow.
- **Deprecate, then remove — never surprise.** Emit a deprecation warning *and* mark the name so
  type checkers and IDEs surface it; state the replacement and the removal version in the message;
  keep the old path working for at least one minor release; remove only in a major.
- **Design for extension without breakage**: keyword-only parameters can be added freely — another
  reason for `*` in signatures. Returned objects grow fields, so callers must not destructure
  exhaustively.
- **Renames are re-exports first**: the old name lives on as a deprecated alias of the new one,
  never a copy.

## Implementation-Specific Dependencies Live in the Implementation

When an interface has several implementations and each needs its own library, that library is
imported **only in the module of the implementation that uses it** — never in the interface module,
the factory, the package `__init__.py`, or anything above the implementation.

- **One implementation — one module — its own imports at the top of that module.** The directory
  those modules share, and what else belongs in it, is in `core.md`.
- **The interface module imports nothing implementation-specific.** If it needs a type from a
  library for a signature, that is a leak — define a domain type or a contract of your own instead.
- **The factory does not import all implementations at module top.** Doing so makes importing the
  package pull in every driver, so a service that only ever uses the local implementation still
  pays the import cost and must have the library installed. The dispatch mapping holds *local
  builders*, and each builder imports its own driver inside itself. For an open set of
  implementations, invert it: a registry each implementation module registers itself with, or entry
  points.
- **Optional libraries are optional extras**, and the implementation module is the only place that
  fails when the extra is missing. Convert the import failure into the package's own error, naming
  the extra to install. **This is checkable, and prose is not enough**: a `forbidden` import
  contract bans the library from the whole package and lists every permitted edge — see
  the `python-wiring` skill.
- **Tests for an implementation are skipped, not failed, when its library is absent.**
- **The same rule applies to implementation-specific settings**: they belong to that
  implementation, not to the shared settings root.

  ```python
  # WRONG — the package __init__ loads and requires every driver just to be imported
  from .local import LocalBlobStore
  from .s3 import S3BlobStore          # pulls the cloud SDK in with it

  def create_blob_store(kind: str) -> BlobStore: ...
  ```

  ```python
  # CORRECT — the contract knows nothing, and only the chosen driver is ever imported
  class BlobStore(ABC):
      @abstractmethod
      def put(self, key: str, data: bytes) -> None: ...


  class _BlobStoreOptions(TypedDict):
      bucket: NotRequired[str]
      region: NotRequired[str]
      root: NotRequired[Path]


  type _Factory = Callable[..., BlobStore]


  # Each builder declares the options it uses and swallows the rest, so the dispatcher never
  # has to know the union of what its builders might want.
  def _s3(*, bucket: str, region: str, **_: object) -> BlobStore:
      from .s3 import S3BlobStore   # noqa: PLC0415  # optional extra, loaded on demand
      return S3BlobStore.create(bucket, region)


  def _local(*, root: Path, **_: object) -> BlobStore:
      from .local import LocalBlobStore   # noqa: PLC0415
      return LocalBlobStore(root)


  _FACTORY: Final[Mapping[BlobStoreKind, _Factory]] = MappingProxyType(
      {
          BlobStoreKind.S3: _s3,
          BlobStoreKind.LOCAL: _local,
      }
  )


  def create_blob_store(kind: BlobStoreKind, **options: Unpack[_BlobStoreOptions]) -> BlobStore:
      return _FACTORY[kind](**options)
  ```

  The mapping is built at import time out of *local* functions, so nothing heavy is loaded; the
  driver arrives only when the builder that needs it runs. Callers name concrete fields, never a
  settings object:

  ```python
  store = create_blob_store(
      settings.blob_store_kind,
      bucket=settings.s3_bucket,
      region=settings.s3_region,
      root=settings.blob_root,
  )
  ```

## A Façade Over Per-Extra Modules

When the package exports its implementations by name — `from acme.instrumentation import
instrument_fastapi` — the package's `__init__` executes *every* implementation module, and a
consumer holding one extra gets `ImportError` on a library it never asked for. Three shapes work:

- **No façade**: `__init__` stays empty and consumers import the module they need
  (`acme.instrumentation.fastapi`). Imports stay at module top; nothing is lazy.
- **Façade, and the library is imported inside the function that uses it.** The module then imports
  cleanly without its library, and the failure arrives to whoever called the function — with the
  extra named. This is the shape below.
- **Façade, and the export itself is lazy** — the `TYPE_CHECKING` plus `__getattr__` pattern above.
  Worth it when the modules are many or expensive; the per-function import is simpler when they
  are few, and simpler wins by default.

  ```python
  # acme/_errors.py — one root for the package, one base that builds the message
  class AcmeError(Exception):
      """Everything this package refuses with."""


  class MissingExtraError(AcmeError, ImportError):
      """An instrumentation is asked for and its library is not in the environment.

      Catch this root for "some extra is missing", or a leaf when it matters which. The root is
      never raised on its own: the leaf names the extra, and without one there is no message.
      """

      extra: ClassVar[str]

      def __init__(self) -> None:
          super().__init__(f"instrumentation needs acme[{self.extra}]")


  # acme/instrumentation/sqlalchemy.py — the module imports cleanly without its library
  """Tracing for database calls. Installed with the `sqlalchemy` extra."""

  from __future__ import annotations

  from typing import TYPE_CHECKING, final

  from acme._errors import MissingExtraError

  if TYPE_CHECKING:
      from sqlalchemy.ext.asyncio import AsyncEngine

      from acme._telemetry import Telemetry


  @final
  class SqlalchemyMissingExtraError(MissingExtraError):
      """The database instrumentation is not in the environment."""

      extra = "sqlalchemy"


  def instrument_sqlalchemy(telemetry: Telemetry, engine: AsyncEngine) -> None:
      """Trace database calls made through this engine.

      Args:
          telemetry: The telemetry set up for this process.
          engine: The engine whose statements are traced.

      Raises:
          SqlalchemyMissingExtraError: If the instrumentation is not installed.
      """
      try:
          # Optional extra: imported on demand, not when the module is imported.
          from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # noqa: PLC0415
      except ImportError as error:
          raise SqlalchemyMissingExtraError from error

      SQLAlchemyInstrumentor().instrument(
          engine=engine.sync_engine,
          tracer_provider=telemetry.tracer_provider,
      )


  # acme/instrumentation/__init__.py — the façade is now free: no module executes its library
  from acme.instrumentation.sqlalchemy import (
      SqlalchemyMissingExtraError as SqlalchemyMissingExtraError,
      instrument_sqlalchemy as instrument_sqlalchemy,
  )

  __all__ = ["SqlalchemyMissingExtraError", "instrument_sqlalchemy"]
  ```

The extra is named **once**, by the class that refuses. A constant beside the function and an
argument passed into the error are two places to drift from what the package metadata declares.
