# Paths, Uploads and Archives

### A path from outside input is resolved, then checked component by component against its base

**Why:** a string prefix check passes `../../etc/passwd` and `/srv/proofs-old` alike; `resolve()`
removes `..` and follows symlinks, and `is_relative_to` compares path components, not characters.

**Example:**
```python
# WRONG — "../../etc/passwd" still starts with the root string, and so does "/srv/proofs-old"
def proof_file_path(proof_root: Path, filename: str) -> Path:
    path = proof_root / filename
    if not str(path).startswith(str(proof_root)):
        raise ProofPathEscapeError(filename)
    return path


# CORRECT — resolve ".." and symlinks first, then compare path components
def proof_file_path(proof_root: Path, filename: str) -> Path:
    path = (proof_root / filename).resolve()
    if not path.is_relative_to(proof_root.resolve()):
        raise ProofPathEscapeError(filename)
    return path
```

### An upload is stored under a generated name; the user's name is data for display

**Why:** the user's filename as the path is `..`, a device name, or another upload's name.

### A tar archive is extracted with `filter="data"`

**Why:** an entry named `../../.ssh/authorized_keys` writes wherever it points. The `data` filter
refuses absolute paths, `..`, links leaving the destination and device files; it is the default
from 3.14, and below that the argument is mandatory, because the old default trusted every entry.

**Example:**
```python
# WRONG — below 3.14 every entry is trusted, "../../.ssh/authorized_keys" included
def unpack_print_bundle(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path) as archive:
        archive.extractall(destination)


# CORRECT — the data filter raises on absolute paths, "..", outside links and device files
def unpack_print_bundle(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path) as archive:
        archive.extractall(destination, filter="data")
```
