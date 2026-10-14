# `__init__.py`, `_internal/` and Lazy Exports

## Private Sub-Package

### The private area is `_internal/`, with the underscore, and its `__init__.py` is empty

**Why:** the name is the boundary, not a docstring. NumPy shipped `numpy/core/` documented as
private but named public; downstream imported from it for years, and undoing that took a NEP,
compatibility stubs and a lint rule. `pydantic` and `pip` ship `_internal/`; there is no contract
to declare there, so internal code imports the module it needs and
`pydantic/_internal/__init__.py` is zero bytes.

### Whether the modules inside repeat the underscore is decided once for the whole area

**Why:** PEP 8 says they need not — *"An interface is also internal if any containing namespace is
internal"* — and `pip` keeps plain `cli/` and `models/` inside `_internal/`; `pydantic` prefixes all
twenty-eight, so a module seen alone in a traceback still says what it is. Either works; a tree
where half carry the prefix leaves nobody able to say which half is deliberate.

## A Library's Facade

### A library facade holds a version guard, a deprecation shim and lazy exports, nothing more

**Why:** logic in `__init__.py` runs on every import of anything below it, in an order nobody
chose. Three things earn their place: a guard that fails fast on an incompatible environment —
`pydantic` checks its compiled core's version on the first line and deletes the helper afterwards;
a shim for a moved name (`deprecation.md`); and lazy exports, below.

### A facade over many or heavy submodules imports them on first access, declared for the checker

**Why:** an eager facade makes `import hues` pay for the whole library, including parts this process
never touches. A name served by `__getattr__` is invisible to the type checker, so the same imports
are declared again under `TYPE_CHECKING`. Every list names the same names, and a test asserts it —
in the library this shape comes from, three lists disagree in order and by four names. `__dir__`
returning `__all__` keeps completion honest. An unknown name raises `AttributeError`, never the
table's `KeyError`: `hasattr`, `getattr` with a default and `from package import submodule` expect
the former.
**Except:** never to compute names, to export what is not a real attribute of a real module, or in
an application package, where import cost was never the problem.

**Example:**
```python
# WRONG — hues/__init__.py: every exporter, and its imaging and PDF libraries, load on import
from hues.exporters.pdf import PdfSwatchSheet
from hues.exporters.png import PngSwatchStrip

__all__ = ["PdfSwatchSheet", "PngSwatchStrip"]


# CORRECT — hues/__init__.py, the whole file: the imports are the pattern
from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from hues.exporters.pdf import PdfSwatchSheet
    from hues.exporters.png import PngSwatchStrip

__all__ = ["PdfSwatchSheet", "PngSwatchStrip"]

_MODULE_BY_NAME: Final = {
    "PdfSwatchSheet": "hues.exporters.pdf",
    "PngSwatchStrip": "hues.exporters.png",
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
