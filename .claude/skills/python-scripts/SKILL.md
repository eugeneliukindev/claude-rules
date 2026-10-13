---
name: python-scripts
description: >-
  Says which rules relax for one-off scripts, notebooks and data fixes and which never do; PEP 723
  metadata, dry-run by default, the point a script stops being one. Use when writing a standalone
  script, a notebook, a backfill script or a data fix, or a file with a '# /// script' block.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Scripts

The rules in this directory were written for code that lives — a service, a library, a worker — and
models over-apply them: a forty-line script that renames files once does not improve by growing a
contract, a fake and a composition root. A script is a file run by hand or by one person's one-off
job, imported by nothing, read by its author — a data fix, a report, a backfill, a notebook. Where
it uses a library, that library's skill still holds: a token it acts on is verified as
`python-pyjwt` says, a call to a gRPC service is made as `python-grpc` says.

### A file stops being a script once it is imported, scheduled, run by others, or outgrows a screen

**Why:** from the next edit on, every rule applies. The signals are: something imports it or copies
a function out of it; it runs on a schedule, or in production with nobody watching; someone other
than its author is expected to run it; `main()` no longer fits on a screen — a few hundred lines in
all. The promotion is a move, not a rewrite: the functions go into a package, and the contracts,
fakes and tests arrive with the second implementation or the first test, as they would anywhere.

### A script calls its one implementation directly: no contract, no fake, no composition root

**Why:** an ABC with a single implementation in a file nobody imports is ceremony, and so are a
fake, layers, `__init__.py`, `__all__` and the `_` prefix, which tell an importer what is internal
when there is no importer. A script is verified by running it — on a copy of the data, or dry-run
first; a function in it subtle enough to need a test is the first sign of a promotion. The module
docstring says in one line what it does and how it is run.

**Example:**
```python
# WRONG — a contract, an implementation and a root, for one CSV read once
class StatusSource(ABC):
    @abstractmethod
    def statuses(self) -> Iterator[str]: ...


@final
class CsvStatusSource(StatusSource):
    def __init__(self, *, path: Path) -> None:
        self._path = path

    @override
    def statuses(self) -> Iterator[str]:
        with self._path.open(encoding="utf-8", newline="") as source:
            yield from (row["status"] for row in csv.DictReader(source))


def main() -> None:
    source: StatusSource = CsvStatusSource(path=Path(sys.argv[1]))
    print(Counter(source.statuses()))


# CORRECT — one function, called from main()
def count_statuses(path: Path) -> Counter[str]:
    with path.open(encoding="utf-8", newline="") as source:
        return Counter(row["status"] for row in csv.DictReader(source))


def main() -> None:
    print(count_statuses(Path(sys.argv[1])))
```

### The statements still live in `main()` and functions, never at module level

**Why:** `main()` builds what it needs — the pool, the client — and uses it inside a `with`;
statements at module level run on import, so the file cannot be imported by a test or promoted
without running.

### The standard library comes first, and any other package is declared in the script's own header

**Why:** `json` rather than `orjson`, `argparse` rather than a CLI framework; a dependency is worth
it when it replaces real code — a spreadsheet writer, a database driver. Declared in the PEP 723
block, it runs anywhere with one command and never against whatever happens to be installed:
`uv run script.py` builds an isolated environment from the block,
`uv add --script script.py 'openpyxl>=3.1'` edits it, `uv lock --script script.py` writes
`script.py.lock` for a script that must give the same result in a month.
`#!/usr/bin/env -S uv run --script` as the first line makes the file executable.

**Example:**
```python
# WRONG — assumes openpyxl is installed wherever the script happens to run
"""Convert the nightly export to a spreadsheet. Run: python export_to_xlsx.py CSV."""

import openpyxl

# CORRECT — the header declares the floor and the dependency; uv run builds the environment
# /// script
# requires-python = ">=3.12"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Convert the nightly export to a spreadsheet. Run: uv run export_to_xlsx.py CSV."""

import openpyxl
```

### Under `basicConfig`, what the reader must see goes in the message, not in `extra=`

**Why:** plain-text logging is enough for a script, and `basicConfig`'s format prints no `extra=`
field — the name of a skipped item passed there never reaches the terminal. The counts the reader
must see go to stderr at the end.

**Example:**
```python
# WRONG — prints "target exists, skipped" and nothing about which file
logger.warning("target exists, skipped", extra={"file_name": source.name})

# CORRECT — the file's name is in the message basicConfig prints
logger.warning("target exists, skipped: %s", source.name)
```

### What fails on exactly the run that mattered never relaxes

**Why:** a script is the code most often run once against production data. What holds there:
- a timeout on every network call (`python-boundaries`);
- secrets from the environment, never in the file — scripts get pasted into chats and committed;
- `encoding="utf-8"` on every text file, `Decimal` for money, aware UTC datetimes;
- a narrow `except` and no swallowed error — a script that "finished" after silently skipping half
  the rows is worse than one that crashed;
- the failure boundary from `principles.md`: one row, one file, one request recorded and counted,
  the count reported at the end, and a non-zero exit code when it is not zero;
- subprocess argument lists and parameterized SQL (`python-security`);
- a key written to a shared cache carries a TTL and never holds a pickle (`python-caching`);
- annotated signatures — the cheapest part of a later promotion, and mypy still finds the `None`
  passed where a value was required.

**Example:**
```python
# WRONG — urlopen has no default timeout: a server that stops answering holds the script forever
def fetch_export(export_url: str) -> bytes:
    with urllib.request.urlopen(export_url) as response:
        export: bytes = response.read()
    return export


# CORRECT — even a one-off waits for a stated time, then fails and says so
def fetch_export(export_url: str) -> bytes:
    with urllib.request.urlopen(export_url, timeout=TIMEOUT_SECONDS) as response:
        export: bytes = response.read()
    return export
```

## A Script That Changes Data

**Before writing a script that changes data — a fix, a backfill, a replay — read
[data-fixes.md](data-fixes.md)** — dry run by default, a journal of what changed, a second run that
changes nothing, a replay under the original event ids, and a complete example.

## Notebooks

**Before writing or committing a notebook, read [notebooks.md](notebooks.md)** — restart and run all
before sharing, outputs cleared of secrets and customer rows, surviving code moved to a module.
