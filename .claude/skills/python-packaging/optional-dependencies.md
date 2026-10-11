# Optional Dependencies

## Contents

- A library one implementation needs is imported only in that implementation
- The factory's builders import their driver themselves
- A missing extra is the package's own error, naming the extra
- An implementation's tests skip when its library is absent

The directory implementations share, and what else belongs in it, is in `python-contracts`; the
contract that bans the library from the rest of the package is in `python-layers`.

### A library one implementation needs is imported only in that implementation's module

**Why:** imported in the contract module, the factory, the package `__init__.py` or anything above,
it makes every importer install it and pay for its import. A library type in the contract's
signature is a leak — the contract defines a domain type of its own. Implementation-specific
settings belong to that implementation, not to the shared settings root.

**Example:**
```python
# WRONG — atlas/storage/base.py: the contract speaks boto3, so every store imports it
from mypy_boto3_s3.type_defs import GetObjectOutputTypeDef


class TileStore(ABC):
    @abstractmethod
    def read(self, key: TileKey) -> GetObjectOutputTypeDef: ...


# CORRECT — the contract speaks its own types; only atlas/storage/s3.py imports boto3
class TileStore(ABC):
    @abstractmethod
    def read(self, key: TileKey) -> Tile | None: ...
```

### The factory's builders import their driver themselves

**Why:** a factory that imports every implementation at its top pulls every driver into a service
that uses one, and fails unless all are installed. The dispatch mapping holds local builders, each
importing its own driver when it runs. For an open set, a registry or entry points, loaded by one
explicit call in the composition root (`python-metaclasses` has why an import-time registry fails).

**Example:**
```python
# WRONG — importing the factory imports both cloud SDKs
from .gcs import GcsBlobStore
from .s3 import S3BlobStore

_FACTORY: Final[Mapping[BlobStoreKind, Callable[[str], BlobStore]]] = MappingProxyType(
    {BlobStoreKind.GCS: GcsBlobStore, BlobStoreKind.S3: S3BlobStore},
)


def create_blob_store(kind: BlobStoreKind, *, bucket: str) -> BlobStore:
    return _FACTORY[kind](bucket)


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

### A missing extra is the package's own error, naming the extra, raised where it is needed

**Why:** a facade that exports implementations by name — `from atlas.exporters import
export_spreadsheet` — runs every implementation module, and a user holding one extra gets an
`ImportError` for a library they never asked for. Three shapes work: no facade, so users import
the module they need; a facade whose functions import their library inside, below; or lazy exports
(`lazy-exports.md`), worth it when the modules are many or expensive. The refusal is an
`ImportError` subclass under the package's root that names the extra — the message is the fix —
and `from error` keeps the failed import in the traceback.

**Example:**
```python
# WRONG — atlas/exporters/spreadsheet.py: importing the facade fails without the extra
import sheetwriter


def export_spreadsheet(places: Sequence[Locality], path: Path) -> None:
    sheetwriter.write(path, [place.as_row() for place in places])


# CORRECT — the module imports cleanly; the caller who needs the extra is told which one
def export_spreadsheet(places: Sequence[Locality], path: Path) -> None:
    try:
        import sheetwriter  # noqa: PLC0415  # optional extra, needed only when called
    except ImportError as error:
        raise MissingExtraError(extra="spreadsheet") from error

    sheetwriter.write(path, [place.as_row() for place in places])
```

### An implementation's tests skip when its library is absent, and the refusal is tested on purpose

**Why:** a missing optional library is a configuration, not a failure. The error a user sees
without the extra is tested by making the import fail: `monkeypatch.setitem(sys.modules,
"sheetwriter", None)` turns `import sheetwriter` into an `ImportError`.

**Example:**
```python
# WRONG — the test module fails to collect wherever the extra is not installed
import sheetwriter


def test_export_spreadsheet_writes_one_row_per_place(tmp_path: Path) -> None:
    export_spreadsheet([_BERLIN], tmp_path / "places.xlsx")

    assert sheetwriter.read(tmp_path / "places.xlsx") == [_BERLIN.as_row()]


# CORRECT — skipped without the extra, and the refusal tested with the import made to fail
sheetwriter = pytest.importorskip("sheetwriter")


def test_export_spreadsheet_writes_one_row_per_place(tmp_path: Path) -> None:
    export_spreadsheet([_BERLIN], tmp_path / "places.xlsx")

    assert sheetwriter.read(tmp_path / "places.xlsx") == [_BERLIN.as_row()]


def test_export_spreadsheet_names_missing_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "sheetwriter", None)

    with pytest.raises(MissingExtraError, match="spreadsheet"):
        export_spreadsheet([_BERLIN], tmp_path / "places.xlsx")
```
