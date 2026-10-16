---
name: python-scripts
description: >-
  Says which rules relax for one-off scripts, notebooks and data fixes and which never do: PEP 723
  metadata, dry-run by default, the point a script stops being one. ALWAYS invoke this skill when a
  task asks for a one-off, a script run once or by hand, a backfill, a data fix, a notebook, or a
  file with a '# /// script' block. Do not write the script directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/*.ipynb"
---

# Scripts

The rules in this directory were written for code that lives - a service, a library, a worker - and
models over-apply them: a forty-line script that renames files once does not improve by growing a
contract, a fake and a composition root. A script is a file run by hand or by one person's one-off
job, imported by nothing, read by its author - a data fix, a report, a backfill, a notebook. A
token it acts on is still verified, and a backfill against a live table is still batched and
bounded; this skill is the script around them.

### A file stops being a script once it is imported, scheduled, run by others, or outgrows a screen

**Why:** from the next edit on, every rule applies. The signals are: something imports it or copies
a function out of it; it runs on a schedule, or in production with nobody watching; someone other
than its author is expected to run it; `main()` no longer fits on a screen - a few hundred lines in
all. The promotion is a move, not a rewrite: the functions go into a package, and the contracts,
fakes and tests arrive with the second implementation or the first test, as they would anywhere.

### A script calls its one implementation directly: no contract, no fake, no composition root

**Why:** an ABC with one implementation in a file nobody imports is ceremony, and so are fakes
(`testing.md`), layers, `__init__.py`, `__all__` and the `_` prefix (`modules.md`). A function
reads its constants where it stands: the defaulted setting of `functions.md` is for code a test
calls. A script is verified by running it - on a copy of the data, or dry-run first; a function
subtle enough to need a test is the first sign of a promotion. The module docstring
says in one line what it does and how it is run.

**Example:**
```python
# WRONG - a contract, an implementation and a root, for one CSV read once
class ConditionSource(ABC):
    @abstractmethod
    def conditions(self) -> Iterator[str]: ...

@final
class CsvConditionSource(ConditionSource):
    def __init__(self, *, path: Path) -> None:
        self._path = path

    @override
    def conditions(self) -> Iterator[str]:
        with self._path.open(encoding="utf-8", newline="") as shelf_list:
            yield from (row["condition"] for row in csv.DictReader(shelf_list))

def main() -> None:
    source: ConditionSource = CsvConditionSource(path=Path(sys.argv[1]))
    print(Counter(source.conditions()))

# CORRECT - one function, called from main()
def count_books_by_condition(path: Path) -> Counter[str]:
    with path.open(encoding="utf-8", newline="") as shelf_list:
        return Counter(row["condition"] for row in csv.DictReader(shelf_list))

def main() -> None:
    print(count_books_by_condition(Path(sys.argv[1])))
```

### The statements still live in `main()` and functions, never at module level

**Why:** `modules.md` holds here too: `main()` builds what it needs - the connection, the client -
and uses it inside a `with`, so the file can be imported by a test or promoted without running.

### The standard library comes first, and any other package is declared in the script's own header

**Why:** a dependency earns its place by replacing real code - a spreadsheet writer, a database
driver, never `orjson` for `json`. Declared in the PEP 723 block, it runs anywhere with one
command, never against whatever is installed: `uv run script.py` builds an isolated environment
from the block, `uv add --script script.py 'openpyxl>=3.1'` edits it, `uv lock --script script.py`
pins a script that must give the same result in a month.
`#!/usr/bin/env -S uv run --script` as the first line makes it executable.

**Example:**
```python
# WRONG - assumes openpyxl is installed wherever the script happens to run
"""Turn the shelf list into a spreadsheet for the valuer. Run: python shelf_list_to_xlsx.py CSV."""

import openpyxl

# CORRECT - the header declares the floor and the dependency; uv run builds the environment
# /// script
# requires-python = ">=3.12"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Turn the shelf list into a spreadsheet for the valuer. Run: uv run shelf_list_to_xlsx.py CSV."""

import openpyxl
```

### Under `basicConfig`, what the reader must see goes in the message, not in `extra=`

**Why:** plain-text logging is enough for a script, and `basicConfig`'s format prints no `extra=`
field - the ISBN of a skipped book passed there, as `logging.md` asks of a service, never reaches
the terminal. The counts the reader must see go to stderr at the end.

**Example:**
```python
# WRONG - prints "isbn not in the catalogue, skipped" and nothing about which book
logger.warning("isbn not in the catalogue, skipped", extra={"isbn": isbn})

# CORRECT - the ISBN is in the message basicConfig prints
logger.warning("isbn not in the catalogue, skipped: %s", isbn)
```

### What fails on the run that mattered never relaxes

**Why:** a script is the code most often run once against production data:
- a timeout on every network call;
- secrets from the environment - scripts get pasted and committed;
- `encoding="utf-8"` on every text file, `Decimal` for money, aware UTC datetimes;
- the narrow `except` (`errors.md`) - a run that "finished" skipping half the rows is worse than
  a crash;
- each failed item counted (`principles.md`), and a non-zero exit when any failed;
- subprocess argument lists and parameterized SQL;
- a TTL and no pickle on a shared-cache key;
- annotated signatures (`types.md`).

**Example:**
```python
# WRONG - urlopen has no default timeout: a server that stops answering holds the script forever
def fetch_wanted_titles(wants_url: str) -> bytes:
    with urllib.request.urlopen(wants_url) as response:
        wanted_titles: bytes = response.read()
    return wanted_titles

# CORRECT - even a one-off waits for a stated time, then fails and says so
def fetch_wanted_titles(wants_url: str) -> bytes:
    with urllib.request.urlopen(wants_url, timeout=WANTS_TIMEOUT_SECONDS) as response:
        wanted_titles: bytes = response.read()
    return wanted_titles
```

## A Script That Changes Data

### Dry run is the default, and writing takes `--apply`

**Why:** the first run of a data fix is the one with the bug in it; it should print what it would
do, and the counts it would reach, before anything is written.

**Example:**
```python
# WRONG - the first run writes, so the bug in it is found in the data
def main() -> None:
    parser = argparse.ArgumentParser(description="Strip the hyphens from cover scan names.")
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    renames, _skipped_count = planned_cover_renames(arguments.directory)
    apply_cover_renames(renames, journal=sys.stdout)

# CORRECT - the plan is printed; only --apply writes
def main() -> None:
    parser = argparse.ArgumentParser(description="Strip the hyphens from cover scan names.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    renames, _skipped_count = planned_cover_renames(arguments.directory)
    for source, target in renames:
        print(f"{source.name} -> {target.name}")
    if arguments.apply:
        apply_cover_renames(renames, journal=sys.stdout)
```

### Every change is written to a journal as it is made

**Why:** a count says how much changed, not what; the identifiers of the changed items, one line
each, let the run be audited or undone. Written as each change succeeds, the journal is right even
when the run dies halfway.

**Example:**
```python
# WRONG - the failures are counted, and nothing records which scans were renamed
def apply_cover_renames(renames: Sequence[tuple[Path, Path]]) -> int:
    failed_count = 0
    for source, target in renames:
        try:
            source.rename(target)
        except OSError:
            logger.exception("rename failed: %s", source.name)
            failed_count += 1
    return failed_count

# CORRECT - each rename that succeeded is a line in the journal, written as it happens
def apply_cover_renames(renames: Sequence[tuple[Path, Path]], *, journal: TextIO) -> int:
    failed_count = 0
    for source, target in renames:
        try:
            source.rename(target)
        except OSError:
            logger.exception("rename failed: %s", source.name)
            failed_count += 1
            continue
        journal.write(f"{source}\t{target}\n")
        journal.flush()
    return failed_count
```

## The Complete Script

Dry run by default, the plan printed, a journal on `--apply`, the counts on stderr, and a non-zero
exit when anything was skipped or failed.

```python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Strip the hyphens from cover scan names. Run: uv run unhyphenate_covers.py DIR [--apply]."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TextIO

EXIT_OK: Final = 0
EXIT_INCOMPLETE: Final = 1

logger = logging.getLogger(__name__)

def main() -> None:
    parser = argparse.ArgumentParser(description="Strip the hyphens from cover scan names.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--journal", type=Path, default=Path("cover_renames.tsv"))
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    renames, skipped_count = planned_cover_renames(arguments.directory)
    for source, target in renames:
        print(f"{source.name} -> {target.name}")
    failed_count = 0
    if arguments.apply:
        with arguments.journal.open("a", encoding="utf-8") as journal:
            failed_count = apply_cover_renames(renames, journal=journal)
    verb = "renamed" if arguments.apply else "would rename"
    print(
        f"{verb} {len(renames) - failed_count} of {len(renames)}, "
        f"{skipped_count} skipped, {failed_count} failed",
        file=sys.stderr,
    )
    sys.exit(EXIT_INCOMPLETE if failed_count or skipped_count else EXIT_OK)

def planned_cover_renames(directory: Path) -> tuple[list[tuple[Path, Path]], int]:
    renames = []
    skipped_count = 0
    for source in sorted(directory.glob("*.jpg")):
        target = source.with_name(source.name.replace("-", ""))
        if target == source:
            continue
        # rename() replaces an existing target without asking
        if target.exists():
            logger.warning("unhyphenated scan exists, skipped: %s", source.name)
            skipped_count += 1
            continue
        renames.append((source, target))
    return renames, skipped_count

def apply_cover_renames(renames: Sequence[tuple[Path, Path]], *, journal: TextIO) -> int:
    failed_count = 0
    for source, target in renames:
        try:
            source.rename(target)
        except OSError:
            logger.exception("rename failed: %s", source.name)
            failed_count += 1
            continue
        journal.write(f"{source}\t{target}\n")
        journal.flush()
    return failed_count

if __name__ == "__main__":
    main()
```

## Notebooks

### A notebook is restarted and run top to bottom before its result is shared

**Why:** cells run out of order leave state no reader can reproduce - a variable from a deleted
cell, a dataframe filtered twice - and a notebook whose result depends on it has no result.
Executing it headless from a clean kernel is the check.

### Outputs that hold a token or a customer's row are cleared before the notebook is committed

**Why:** outputs are part of the `.ipynb` file; a printed token or a displayed row of customer data
is committed and pushed with it, and stays in the history after the cell is fixed.

### Code that survives the exploration moves to a module the notebook imports

**Why:** a function copied from one notebook into the next is a module not yet written, and each
copy drifts on its own. In the module the full rules apply, and it can be tested.

