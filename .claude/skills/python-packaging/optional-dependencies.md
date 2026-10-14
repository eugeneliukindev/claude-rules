# Optional Dependencies

## Contents

- A library one implementation needs is imported only in that implementation
- The factory's builders import their library themselves
- A missing extra is the package's own error, naming the extra
- An implementation's tests skip when its library is absent

### A library one implementation needs is imported only in that implementation's module

**Why:** imported in the contract module, the factory, the package `__init__.py` or anything above,
it makes every importer install it and pay for its import. A library type in the contract's
signature is a leak — the contract defines a domain type of its own. Settings specific to one
implementation belong to it, not to the shared settings root.

**Example:**
```python
# WRONG — hues/sampling/base.py: the contract speaks Pillow, so every sampler imports it
from PIL.Image import Image


class PixelSource(ABC):
    @abstractmethod
    def load(self, path: Path) -> Image: ...


# CORRECT — the contract speaks its own types; only hues/sampling/pillow.py imports Pillow
class PixelSource(ABC):
    @abstractmethod
    def load(self, path: Path) -> Sequence[Colour]: ...
```

### The factory's builders import their library themselves

**Why:** a factory that imports every implementation at its top pulls every library into a process
that uses one, and fails unless all are installed. The dispatch mapping holds local builders, each
importing its own module when it runs — one of the reasons `modules.md` allows a function-level
import. An open set is a registry or entry points, loaded by one explicit call in the composition
root.

**Example:**
```python
# WRONG — importing the factory imports both the PDF and the imaging library
from .pdf import PdfSwatchSheet
from .png import PngSwatchStrip

_BUILDER_BY_SHEET_FORMAT: Final[Mapping[SheetFormat, Callable[[], PaletteExporter]]] = (
    MappingProxyType({SheetFormat.PDF: PdfSwatchSheet, SheetFormat.PNG: PngSwatchStrip})
)


def create_palette_exporter(sheet_format: SheetFormat) -> PaletteExporter:
    return _BUILDER_BY_SHEET_FORMAT[sheet_format]()


# CORRECT — the builders are local, and only the chosen library is ever imported
def _pdf() -> PaletteExporter:
    from .pdf import PdfSwatchSheet  # noqa: PLC0415  # optional extra, loaded on demand

    return PdfSwatchSheet()


def _png() -> PaletteExporter:
    from .png import PngSwatchStrip  # noqa: PLC0415  # optional extra, loaded on demand

    return PngSwatchStrip()


_BUILDER_BY_SHEET_FORMAT: Final[Mapping[SheetFormat, Callable[[], PaletteExporter]]] = (
    MappingProxyType({SheetFormat.PDF: _pdf, SheetFormat.PNG: _png})
)


def create_palette_exporter(sheet_format: SheetFormat) -> PaletteExporter:
    return _BUILDER_BY_SHEET_FORMAT[sheet_format]()
```

### A missing extra is the package's own error, naming the extra, raised where it is needed

**Why:** a facade that exports implementations by name — `from hues.exporters import export_ase`
— runs every implementation module, and a user holding one extra gets an `ImportError` for a
library they never asked for. Three shapes work: no facade, so users import the module they need;
a facade whose functions import their library inside, below; or lazy exports (`init.md`), worth it
when the modules are many or expensive. The refusal is an `ImportError` subclass under the
package's root that names the extra — the message is the fix — and `from error` keeps the failed
import in the traceback.

**Example:**
```python
# WRONG — hues/exporters/ase.py: importing the facade fails without the extra
import asewriter


def export_ase(palette: Palette, path: Path) -> None:
    asewriter.write(path, [colour.hex_code for colour in palette.colours])


# CORRECT — the module imports cleanly; the caller who needs the extra is told which one
def export_ase(palette: Palette, path: Path) -> None:
    try:
        import asewriter  # noqa: PLC0415  # optional extra, needed only when called
    except ImportError as error:
        raise MissingExtraError(extra="ase") from error

    asewriter.write(path, [colour.hex_code for colour in palette.colours])
```

### An implementation's tests skip when its library is absent, and the refusal is tested on purpose

**Why:** a missing optional library is a configuration, not a failure. The error a user sees
without the extra is tested by making the import fail: `monkeypatch.setitem(sys.modules,
"asewriter", None)` turns `import asewriter` into an `ImportError`. The test module is
skipped with `asewriter = pytest.importorskip("asewriter")`, never a top-level `import asewriter`
that fails collection wherever the extra is absent.
