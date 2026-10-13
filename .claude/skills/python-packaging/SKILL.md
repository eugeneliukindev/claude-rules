---
name: python-packaging
description: >-
  Designs a package's public surface: the facade, public and internal modules, __all__, _internal,
  lazy exports, stability tiers, deprecation, optional extras, the prefix check. Use when building
  a package other code imports, editing __init__.py or __all__, adding an optional extra,
  deprecating a name, or choosing between a.b and a._b.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Packaging and Public Surface

The underscore rule for names inside a module is in `modules.md`; this file is about the surface a
package promises and where each module sits on it.

| Level | How it is marked | Who may import it | What it guarantees |
|---|---|---|---|
| Public | listed in the package's `__init__.py` `__all__` | anyone | follows the deprecation rules |
| Package-internal | a module named `_name.py`, or an `_internal/` sub-package | only modules inside that package | may change in any release |
| Module-private | a name prefixed `_` inside a module | only that module | may change at any time |

The underscore does nothing at runtime except exclude the name from a star import; its value is
social and static — a reader sees the decision in a listing, a grep or a traceback, and the linters
flag private names imported across modules.

## Facade, Public Module or Internal Module

| Where it lives | Imported as | It belongs there when |
|---|---|---|
| facade `package/__init__.py` | `from package import Name` | nearly every importer needs the name, and it is light: importing the package pulls no heavy or optional library. The facade fits on one screen |
| public module `package/topic.py`, or sub-package `package/topic/` with its own facade | `from package.topic import Name` | only some importers need it; or it pulls a heavy or optional library; or the names are many; or the module name clarifies the call site (`errors`, `models`, `testing`) |
| internal module `package/_topic.py` | only by modules inside `package` | it is an implementation detail |

### Who imports a name decides where it lives, and the facade stays light

**Why:** a facade that re-exported every capability made a scheduled job that needed one enum
import a headless-browser driver and an ORM on every run, and slowed every import of the package.
The facade carries the vocabulary nearly every importer needs; a heavy or occasional capability is
a public module its few callers import. A sub-package replaces a module when the topic grows its
own internals, and its `__init__.py` is a facade by the same rules.

**Example:**
```python
# WRONG — atlas/__init__.py: `import atlas` loads the imaging library and the ORM
from atlas._places import Coordinates, Place
from atlas._rendering import render_map_png
from atlas._storage import PostgresPlaceRepository

__all__ = ["Coordinates", "Place", "PostgresPlaceRepository", "render_map_png"]


# CORRECT — atlas/__init__.py: the vocabulary only; callers who render import atlas.maps
from atlas._places import Coordinates, Place

__all__ = ["Coordinates", "Place"]
```

### A name has one public path

**Why:** two spellings of one import drift apart, and a grep for its users finds half of them.
**Except:** the two-path shape of `pydantic` and `sqlalchemy` — public modules with their own
`__all__`, re-exported by the facade on purpose — holds only with a test that every module's
`__all__` is contained in the facade's. One shape per package; the default is the flat facade of
`httpx` and `attrs`, implementation in private modules and every public name exported once.

### An internal module is imported only inside its package, and siblings import it directly

**Why:** a reach-in from outside turns an implementation detail into surface nobody reviewed; when
outside code needs it, it becomes a public module, renamed and reviewed. Inside, a sibling that
imports through its own `__init__` makes load order significant and invites a cycle. An
import-linter `protected` contract makes the reach-in fail the build (`python-layers`).

## `__all__`

### `__all__` is literal strings, sorted or grouped by its length

**Why:** a computed or conditionally appended `__all__` is a surface no reader and no type checker
can see. Up to a screenful it is alphabetical — a reader checks membership by scanning; past that,
grouping under topic comments is what a reader navigates (`pydantic` exports 151 names under 21
comments). `from ._places import Place as Place` is PEP 484's other way to declare a re-export; one
form per package. List or tuple is a project's choice.

### A top-level name is either in `__all__` or private

**Why:** a public-looking name that is not exported is a promise nobody made and everybody will
rely on; a private name another package needs is promoted deliberately, with the deprecation
guarantees that brings — copying it is worse. Deep paths that must stay importable, such as plugin
entry points, are a documented part of the surface.

### A script finds the names that should be private; nobody reads for them

**Why:** the `modules.md` test — grep each top-level name, drop its own file, prefix what has no
hits left — is mechanical, and a reading misses names. Run it after a move or a split, and before
declaring `__all__`. Each `path:line: name` is a name to prefix, exit code 1 means there was one; a
line marked `(decorated: unverifiable)` may be handed to a framework by its decorator, so it is
decided by hand. `--exclude` drops a tree whose uses should not count.

### A typed package ships `py.typed`, and a test pins its surface

**Why:** without `py.typed` consumers get `Any` for the whole API. A test asserts `__all__` equals
the intended surface, so an accidental export fails; a second imports the facade in a fresh
interpreter and asserts the heavy modules are absent — the checkable form of "the facade stays
light", which prose alone did not keep.

**Example:**
```python
# WRONG — the surface is checked by nobody, and a heavy import arrives unnoticed
def test_atlas_imports() -> None:
    import atlas

    assert atlas.Place is not None


# CORRECT — the exports and the import cost are both asserted
_PUBLIC_NAMES: Final = frozenset({"Coordinates", "Place"})
_HEAVY_MODULES: Final = ("PIL", "sqlalchemy")


def test_atlas_exports_exactly_its_surface() -> None:
    assert frozenset(atlas.__all__) == _PUBLIC_NAMES


def test_atlas_import_loads_no_heavy_module() -> None:
    probe = f"import atlas, sys; print([m for m in {_HEAVY_MODULES!r} if m in sys.modules])"

    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, encoding="utf-8", check=True
    ).stdout.strip()

    assert loaded == "[]"
```

## Hiding a Whole Subsystem

**Before creating a private sub-package, or deciding whether modules inside one take the `_`
prefix, read [internal.md](internal.md)** — `_internal/` with the underscore, one prefix choice for
the whole area, an empty `__init__.py`.

## `__init__.py` and Lazy Exports

**Before putting anything other than imports and `__all__` into an `__init__.py`, or making a
facade import its submodules on first access, read [lazy-exports.md](lazy-exports.md)** — what a
library facade may hold, `TYPE_CHECKING` plus `__getattr__`, the lists that must agree.

## Stability Tiers

**Before shipping an experimental, deprecated or previous-major part of a library, read
[stability-tiers.md](stability-tiers.md)** — each tier is a package, its `__init__.py` states the
contract, a move between tiers is the release event.

## Families of Names

**Before naming a public method or function that has siblings of the same kind, read
[name-families.md](name-families.md)** — namespace prefixes, scope pairs, `with_` copies,
plurality, symmetrical opposites.

## Compatibility and Deprecation

**Before removing, renaming or changing an exported name, a default, a parameter or a raised
exception, or emitting a deprecation warning, read [deprecation.md](deprecation.md)** — what counts
as breaking, deprecate then remove, `@deprecated` and `stacklevel`, tombstones, re-exported
renames.

## Optional Dependencies

**Before importing a library only one implementation needs, adding an optional extra, or exporting
implementations that need different extras from one facade, read
[optional-dependencies.md](optional-dependencies.md)** — the library imported only in its
implementation, local builders in the factory, the package's own error naming the extra.

## A Module Named Like the Standard Library

**Before naming a top-level module, a loose script or a DAG file after a stdlib module — `json`,
`types`, `logging` — read [stdlib-names.md](stdlib-names.md)** — shadowing on `sys.path`, nested
names that are fine, ruff `A005` without strict checking.
