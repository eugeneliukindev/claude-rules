---
name: python-packaging
description: >-
  The public surface of a Python package: the three levels of visibility, when a name belongs in the
  __init__.py facade, in a public module or in an internal _module, __all__ and the flat facade,
  _internal subpackages, lazy exports through TYPE_CHECKING plus __getattr__, stability
  tiers as directories, semantic-versioning and deprecation rules, and keeping an optional
  dependency inside the one implementation module that uses it. Use when building a Python package
  other code imports — a library, an SDK, a shared kernel — or when working with __init__.py,
  optional extras, a facade or a deprecation, or deciding whether to import from a.b or name it a._b.
---

# Packaging and Public Surface

The underscore rule for names inside a module is in `modules.md`; this file is about the surface a
package promises and where each module sits on it.

## The Three Levels of Visibility

| Level | How it is marked | Who may import it | What it guarantees |
|---|---|---|---|
| Public | listed in the package's `__init__.py` `__all__` | anyone | follows the deprecation rules |
| Package-internal | a module named `_name.py` (or, for a library's large private subsystem, an `_internal/` sub-package) | only modules inside that package | may change in any release |
| Module-private | a name prefixed `_` inside a module | only that module | may change at any time |

**What the underscore actually does**: nothing at runtime except excluding the name from a star
import. Its value is entirely social and static — the linters flag imports of private names across
module boundaries. That is enough, provided the convention is followed consistently.

## Facade, Public Module or Internal Module

Every module in a package — application or library — is one of three, and **who imports it decides
which**. The underscore is how a reader sees the decision in a file listing, a grep or a traceback
without opening the facade; a contract is how a tool enforces it.

| Where it lives | Imported as | It belongs there when |
|---|---|---|
| facade `package/__init__.py` | `from package import Name` | nearly every importer of the package needs the name, and it is light: importing the package pulls no heavy or optional library. The facade fits on one screen |
| public module `package/topic.py`, or sub-package `package/topic/` with its own facade | `from package.topic import Name` | only some importers need it; or it pulls a heavy or optional library the facade must not; or the names are many and would bloat the facade; or the module name clarifies the call site (`errors`, `models`, `testing`) |
| internal module `package/_topic.py` | only by modules inside `package` | it is an implementation detail; nothing outside `package` imports it |

- **One public path per name.** A name is in the facade or in a public module, never both: two
  spellings of one import drift apart, and grepping for users finds half of them.
- **A sub-package replaces a module when the topic grows its own internals.** Its `__init__.py` is
  a facade by the same three rules, recursively.
- **An internal module is never imported from outside.** When outside code needs it, it becomes a
  public module — renamed, reviewed as surface — rather than reached into.
- **Inside a package, siblings import the internal module directly** (`from ._topic import ...`),
  never through their own `__init__`, which would make load order significant.

```python
# WRONG — the facade re-exports everything, so `import shop` loads the PDF renderer and the ORM
# shop/__init__.py
from shop._invoices import render_invoice_pdf  # pulls a native PDF library
from shop._orders import Order, OrderStatus
from shop._repository import PostgresOrderRepository  # pulls the ORM and the driver

__all__ = ["Order", "OrderStatus", "PostgresOrderRepository", "render_invoice_pdf"]

# CORRECT — the facade carries the vocabulary; heavy capabilities are public modules imported by
# the few callers that need them: `from shop.invoices import render_invoice_pdf`
# shop/__init__.py
from shop._orders import Order, OrderStatus

__all__ = ["Order", "OrderStatus"]
```

A facade that re-exported every capability made a scheduled job that needed one enum import a
headless-browser driver and an ORM on every run — and slowed every import of the package with it.

**Checked, not remembered**: an import-linter `protected` contract lists the internal modules of a
package and the package itself as their only importer, so a reach-in fails the build instead of a
review.

### Finding Names That Should Be Private

The `modules.md` rule's test — grep each top-level name, drop its own file, prefix what has no hits
left — is scripted. Run it, do not read it:

```bash
python <this skill's directory>/scripts/find_unprefixed_names.py src/yourpackage \
    --exclude "migrations/*"
```

Run it after a move or a split that may have left a public name with no outside user, and before
declaring a package's `__all__`. Each `path:line: name` line is a name to prefix; exit code 1 means
there was at least one. A line marked `(decorated: unverifiable)` has a decorator that may hand it
to a framework — a route, a command, a fixture — so decide it by hand. Pass `--exclude` for a tree
whose uses should not count, such as tests when the question is what production code needs.

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
  internal code imports the module it needs directly. A facade declares a contract, and there is no
  contract to declare here.

## The Flat Public Facade

How the standard library, `pydantic` and `attrs` are built:

- Implementation lives in private modules: `_client.py`, `_models.py`, `_transport.py`.
- `__init__.py` imports the public names from them and lists exactly those in `__all__`.
- Consumers write one stable path regardless of which private module the name currently lives in.
  Deep paths are unsupported by construction.
- Internal code imports from the private modules directly — never through the package's own
  `__init__`, which would create a cycle and make module load order significant.

```python
# acme_core/__init__.py — the whole public surface, and nothing else
from ._identifiers import OrderId, UserId
from ._models import Order, User
from ._repository import UserRepository

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
- **A private name is never imported across a package boundary.** If another package needs it, it is
  not private: promote it deliberately, with the deprecation guarantees that implies. Copying it is
  worse.
- **Deep paths that must stay importable** (plugin entry points) are an explicit, documented part
  of the public surface, not an accident.
- **`py.typed` ships with every typed package**, or consumers get `Any` for the whole API.
- **A test asserts that `__all__` matches the intended surface**, so an accidental export fails.

### What May Live in `__init__.py`

**In an application package: imports and `__all__`, nothing else.** Logic there runs on every
import of anything below it, and it runs in an order nobody chose.

**In a library facade the bar is different**, because the file is a contract rather than a
convenience, and three things earn their place:

- **A guard that fails fast on an incompatible environment.** `pydantic` checks its compiled core's
  version on the first line and deletes the helper afterwards — a mismatch there produces a clear
  error instead of an incomprehensible one three frames deep.
- **A deprecation shim**, so a moved or renamed name keeps working and says so.
- **Lazy exports through `__getattr__`** — the next section.

### Lazy Exports: `TYPE_CHECKING` Plus `__getattr__`

A facade that imports every submodule eagerly makes `import yourpackage` pay for the whole library,
including the parts this process will never touch. The fix is to import on first access, and the
objection — that a name arriving through `__getattr__` is invisible to the type checker — is
answered by declaring the imports a second time under `TYPE_CHECKING`:

```python
# yourpackage/__init__.py
if TYPE_CHECKING:
    # Everything is served lazily by __getattr__ below; these are what the type
    # checker and the IDE read.
    from .validators import AfterValidator, BeforeValidator

__all__ = ["AfterValidator", "BeforeValidator"]

_LAZY: Final = {
    # validators
    "AfterValidator": ".validators",
    "BeforeValidator": ".validators",
}


def __getattr__(name: str) -> object:
    try:
        module_name = _LAZY[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    return getattr(import_module(module_name, __name__), name)
```

The checker reads the `TYPE_CHECKING` block and sees full signatures; the interpreter reads the
table and imports nothing until asked. **Every list must name the same names**, so keep them in
the same order and in the same groups — the only real cost of the pattern is that they can drift,
and side-by-side ordering is what makes the drift visible in a diff. An unknown name raises
`AttributeError`, never the table's `KeyError`: `hasattr`, `getattr` with a default and
`from yourpackage import submodule` all expect the former, and crash on the latter.

Use it in a facade over many submodules, or where one export pulls a heavy optional dependency.
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
  those modules share, and what else belongs in it, is in `python-contracts`.
- **The interface module imports nothing implementation-specific.** If it needs a type from a
  library for a signature, that is a leak — define a domain type or a contract of your own instead.
- **The factory does not import all implementations at module top.** Doing so makes importing the
  package pull in every driver, so a service that only ever uses one implementation still pays
  for every other one's import and must have its library installed. The dispatch mapping holds
  *local builders*, and each builder imports its own driver inside itself. For an open set of
  implementations, invert it: a registry each implementation module registers itself with, or
  entry points.
- **Optional libraries are optional extras**, and the implementation module is the only place that
  fails when the extra is missing. Convert the import failure into the package's own error, naming
  the extra to install. **This is checkable, and prose is not enough**: a `forbidden` import
  contract bans the library from the whole package and lists every permitted edge — see
  the `python-layers` skill.
- **Tests for an implementation are skipped, not failed, when its library is absent.**
- **The same rule applies to implementation-specific settings**: they belong to that
  implementation, not to the shared settings root.

```python
# WRONG — importing the factory imports both cloud SDKs, and fails unless both are installed
from .gcs import GcsBlobStore
from .s3 import S3BlobStore


def _gcs(bucket: str) -> BlobStore:
    return GcsBlobStore(bucket)


def _s3(bucket: str) -> BlobStore:
    return S3BlobStore(bucket)

# ... the same _FACTORY and create_blob_store as below
```

```python
# CORRECT — the builders are local, and only the chosen driver is ever imported
def _gcs(bucket: str) -> BlobStore:
    from .gcs import GcsBlobStore  # noqa: PLC0415  # optional extra, loaded on demand
    return GcsBlobStore(bucket)


def _s3(bucket: str) -> BlobStore:
    from .s3 import S3BlobStore  # noqa: PLC0415  # optional extra, loaded on demand
    return S3BlobStore(bucket)


_FACTORY: Final[Mapping[BlobStoreKind, Callable[[str], BlobStore]]] = MappingProxyType(
    {BlobStoreKind.GCS: _gcs, BlobStoreKind.S3: _s3},
)


def create_blob_store(kind: BlobStoreKind, *, bucket: str) -> BlobStore:
    return _FACTORY[kind](bucket)
```

The mapping is built at import time out of *local* functions, so nothing heavy is loaded; the
driver arrives only when the builder that needs it runs.

## A Facade Over Per-Extra Modules

When the package exports its implementations by name — `from acme.exporters import
export_spreadsheet` — the package's `__init__` executes *every* implementation module, and a
consumer holding one extra gets `ImportError` on a library it never asked for. Three shapes work:

- **No facade**: `__init__` stays empty and consumers import the module they need
  (`acme.exporters.spreadsheet`). Imports stay at module top; nothing is lazy.
- **Facade, and the library is imported inside the function that uses it.** The module then imports
  cleanly without its library, and the failure arrives to whoever called the function — with the
  extra named. This is the shape below.
- **Facade, and the export itself is lazy** — the `TYPE_CHECKING` plus `__getattr__` pattern above.
  Worth it when the modules are many or expensive; the per-function import is simpler when they
  are few, and simpler wins by default.

```python
# acme/exporters/spreadsheet.py — imports cleanly whether or not the extra is installed
def export_spreadsheet(orders: Sequence[Order], path: Path) -> None:
    try:
        import sheetwriter  # noqa: PLC0415  # optional extra, needed only when called
    except ImportError as error:
        raise MissingExtraError(extra="spreadsheet") from error

    sheetwriter.write(path, [order.as_row() for order in orders])


# acme/exporters/__init__.py — the facade is free: no module runs its library on import
from .spreadsheet import export_spreadsheet

__all__ = ["export_spreadsheet"]
```

The refusal is the package's own error, an `ImportError` subclass under its root, and it names the
extra — the message is the fix, and `from error` keeps the import that actually failed in the
traceback.

## A Module Named Like a Standard-Library Module

A module name that reaches `sys.path` directly must not shadow a standard-library module — `types`,
`json`, `logging`, `io`, `abc`. This bites for a top-level module of a distribution, a loose script,
or a scheduler DAG file: `import json` anywhere in the process then gets yours. Nested inside a
package the name is only ever visible as `mypackage.json`, so there is nothing to shadow, and the
module is named after its contents — `internal/json.py` is right. ruff `A005` fires on both, so a
package that names modules after their contents turns `A005` off once, with the reason written down.
