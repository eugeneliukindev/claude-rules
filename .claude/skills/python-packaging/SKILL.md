---
name: python-packaging
description: >-
  Designs a package's public surface: where a name lives, __all__, _internal, lazy exports,
  stability tiers, deprecation, optional extras, the prefix check. Use when building a package
  other code imports, editing __init__.py or __all__, adding an optional extra, deprecating a name,
  or choosing between a.b and a._b. Not for pyproject.toml itself (python-project).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Packaging and Public Surface

The facade, the underscore and function-level imports are `modules.md`; this skill is what a
package others import adds to them. The import-linter contract that fails a reach-in is
`python-layers`.

## Where a Name Lives

| Where it lives | Imported as | It belongs there when | It promises |
|---|---|---|---|
| facade `package/__init__.py` | `from package import Name` | nearly every importer needs it, and it is light; the facade fits on one screen | the deprecation rules |
| public module `package/topic.py`, or sub-package `package/topic/` with its own facade | `from package.topic import Name` | only some importers need it, it pulls a heavy or optional library, the names are many, or the module name clarifies the call site (`errors`, `models`, `testing`) | the deprecation rules |
| internal module `package/_topic.py`, or `package/_internal/` | only by modules inside `package` | it is an implementation detail | nothing, in any release |

### A name has one public path

**Why:** two spellings of one import drift apart, and a grep for its users finds half of them.
**Except:** the two-path shape of `pydantic` and `sqlalchemy` — public modules with their own
`__all__`, re-exported by the facade on purpose — holds only with a test that every module's
`__all__` is contained in the facade's. One shape per package; the default is the flat facade of
`httpx` and `attrs`, implementation in private modules and every public name exported once.

### A sibling imports an internal module directly, never through its own `__init__`

**Why:** an import through the package's own facade makes load order significant and invites a
cycle. Outside code that needs an internal module gets a public module, renamed and reviewed.

## `__all__`

### `__all__` is literal strings, sorted or grouped by its length

**Why:** a computed or conditionally appended `__all__` is a surface no reader and no type checker
can see. Up to a screenful it is alphabetical — a reader checks membership by scanning; past that,
grouping under topic comments is what a reader navigates (`pydantic` exports 151 names under 21
comments). `from ._palette import Palette as Palette` is PEP 484's other way to declare a
re-export; one form per package.

### A top-level name is either in `__all__` or private

**Why:** a public-looking name that is not exported is a promise nobody made and everybody will
rely on; a private name another package needs is promoted deliberately, with the deprecation
guarantees that brings — copying it is worse. Deep paths that must stay importable, such as plugin
entry points, are a documented part of the surface.

### A script finds the names that should be private

**Why:** the test — grep each top-level name, drop its own file, prefix what has no hits left — is
mechanical, and a reading misses names. Run it after a move or a split and before declaring
`__all__`, over the sources and tests together:

```bash
python <this skill's directory>/scripts/find_unprefixed_names.py src/yourpackage
```

Each `path:line: name` is a name to prefix, and exit code 1 means there was one; a line marked
`(decorated: unverifiable)` may be handed to a framework by its decorator, so it is decided by hand.
`--exclude GLOB` drops a tree whose uses should not count.

### A typed package ships `py.typed`, and a test pins its surface

**Why:** without `py.typed` consumers get `Any` for the whole API. A test asserts `__all__` equals
the intended surface, so an accidental export fails; a second imports the facade in a fresh
interpreter and asserts the heavy modules are absent — the checkable form of a light facade, which
prose alone did not keep.

**Example:**
```python
# WRONG — the surface is checked by nobody, and a heavy import arrives unnoticed
def test_hues_imports() -> None:
    import hues

    assert hues.Palette is not None


# CORRECT — the exports and the import cost are both asserted
_PUBLIC_NAMES: Final = frozenset({"Colour", "Palette"})
_HEAVY_MODULES: Final = ("PIL", "numpy")


def test_hues_exports_exactly_its_surface() -> None:
    assert frozenset(hues.__all__) == _PUBLIC_NAMES


def test_hues_import_loads_no_heavy_module() -> None:
    probe = f"import hues, sys; print([m for m in {_HEAVY_MODULES!r} if m in sys.modules])"

    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, encoding="utf-8", check=True
    ).stdout.strip()

    assert loaded == "[]"
```

## `__init__.py`, `_internal/` and Lazy Exports

**Before creating a private sub-package, putting anything but imports and `__all__` into a
library's `__init__.py`, or making a facade import its submodules on first access, read
[init.md](init.md)** — `_internal/` with the underscore and an empty `__init__.py`, one prefix
choice for the area, what a library facade may hold, `TYPE_CHECKING` plus `__getattr__`.

## Families of Names

The shapes worth copying when a public name has siblings of the same kind (`naming.md`):

- **Namespace prefix** — `model_validate`, `model_dump`, `model_copy`: every method of `BaseModel`
  is prefixed, so a user's own field named `dump` never collides.
- **Scope pair** — `field_validator` / `model_validator`: same job, two scopes, one word apart.
- **Derived copy** — `with_only_columns`, `Path.with_suffix`: `with_` returns a copy with X set.
- **Plurality** — `scalar` / `scalars`: singular returns one, plural returns many.
- **Symmetrical opposites** — `open` / `close`, `get_label_style` / `set_label_style`,
  `correlate` / `correlate_except`: one part differs, the rest reads the same.

## Compatibility, Deprecation and Stability Tiers

**Before removing, renaming or changing an exported name, a default, a parameter or a raised
exception, emitting a deprecation warning, or shipping an experimental or previous-major part,
read [deprecation.md](deprecation.md)** — what counts as breaking, `@deprecated` and `stacklevel`,
renames as aliases, tombstones, a tier as a package.

## Optional Dependencies

**Before importing a library only one implementation needs, adding an optional extra, or exporting
implementations that need different extras from one facade, read
[optional-dependencies.md](optional-dependencies.md)** — the library imported only in its
implementation, local builders in the factory, the package's own error naming the extra.

## A Module Named Like the Standard Library

### A module that reaches `sys.path` directly never takes a stdlib name

**Why:** a top-level module of a distribution, a loose script or a scheduler DAG file named `json`,
`types`, `logging`, `io` or `abc` is what `import json` anywhere in the process then gets. Nested
inside a package the name is only ever `mypackage.json`, so nothing is shadowed. ruff `A005`
compares the full dotted path, so it fires on a top-level `src/json.py` and not on
`hues/_internal/json.py` (measured on ruff 0.17); `flake8-builtins.strict-checking` stays off, or
every nested module needs a suppression it has no reason for.
