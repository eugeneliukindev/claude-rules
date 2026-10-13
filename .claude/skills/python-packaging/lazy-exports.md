# `__init__.py` and Lazy Exports

## Contents

- What an application's and a library's `__init__.py` may hold
- Lazy exports: `TYPE_CHECKING` plus `__getattr__`, and when not to use them

### An application package's `__init__.py` holds imports and `__all__`, nothing else

**Why:** logic there runs on every import of anything below it, in an order nobody chose. A library
facade is a contract rather than a convenience, and three things earn their place in it: a guard
that fails fast on an incompatible environment — `pydantic` checks its compiled core's version on
the first line and deletes the helper afterwards; a deprecation shim for a moved name
(`deprecation.md`); and lazy exports, below.

### A facade over many or heavy submodules imports them on first access, declared for the checker

**Why:** an eager facade makes `import yourpackage` pay for the whole library, including parts this
process never touches. A name served by `__getattr__` is invisible to the type checker, so the same
imports are declared again under `TYPE_CHECKING`, where the checker and the IDE read full
signatures. **Every list names the same names**, and a test asserts it — in the library this shape
comes from, three lists already disagree in order and by four names. `__dir__` returning `__all__`
keeps completion honest. An unknown name raises `AttributeError`, never the table's `KeyError`:
`hasattr`, `getattr` with a default and `from package import submodule` expect the former.
**Except:** never to compute names, to export what is not a real attribute of a real module, or in
an application package, where import cost was never the problem.

**Example:**
```python
# WRONG — atlas/__init__.py: every exporter, and its imaging and PDF libraries, load on import
from atlas.exporters.pdf import PdfAtlas
from atlas.exporters.tiles import TileSet

__all__ = ["PdfAtlas", "TileSet"]


# CORRECT — atlas/__init__.py, the whole file: the imports are the pattern
from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from atlas.exporters.pdf import PdfAtlas
    from atlas.exporters.tiles import TileSet

__all__ = ["PdfAtlas", "TileSet"]

_MODULE_BY_NAME: Final = {
    "PdfAtlas": "atlas.exporters.pdf",
    "TileSet": "atlas.exporters.tiles",
}


def __getattr__(name: str) -> object:
    try:
        module_name = _MODULE_BY_NAME[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module_name), name)
    globals()[name] = value  # the next access is a plain attribute, not this function
    return value


def __dir__() -> list[str]:
    return list(__all__)
```
