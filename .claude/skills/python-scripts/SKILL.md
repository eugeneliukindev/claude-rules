---
name: python-scripts
description: >-
  One-off Python scripts, notebooks and data fixes: which rules relax for code that runs a few
  times and is thrown away — contracts, fakes, a composition root, layers, the underscore prefix,
  orjson — and which never do — timeouts, secrets, encodings, Decimal money, aware datetimes, narrow
  excepts, subprocess lists, parameterized SQL; PEP 723 inline metadata run with uv run; dry-run by
  default for a data fix; and the point where a script stops being one. Use when writing a
  standalone .py script, a notebook, a backfill or one-off data migration, a file with a
  "# /// script" block, or anything run by hand with uv run or python script.py.
---

# Scripts

The rules in this directory were written for code that lives — a service, a library, a worker —
and models over-apply them. A forty-line script that renames files once does not improve by
growing a contract, a fake and a composition root: it becomes four times longer and no safer. This
file says what relaxes for a script, what does not, and when a script has stopped being one.

## What a Script Is, and When It Stops Being One

A file run by hand or by one person's one-off job, imported by nothing, read by its author: a data
fix, a report, a backfill, an exploration notebook, a release helper.

**It stops being a script the moment one of these is true**, and from the next edit on every rule
applies:

- something imports it, or another file copies a function out of it;
- it runs on a schedule, or in production with nobody watching;
- someone other than its author is expected to run it;
- `main()` no longer fits on a screen — a few hundred lines in all.

The promotion is a move, not a rewrite: the functions go into a package, and the contracts, fakes
and tests arrive with the second implementation or the first test, as they would anywhere.

## What Relaxes

- **No contracts, no fakes, no `tests/fakes.py`.** One implementation, called directly. An ABC with
  a single implementation in a file nobody imports is ceremony.
- **No separate composition root.** `main()` builds the session or the engine and uses it, inside
  a `with`. It is still `main()` plus functions, not statements at module level — that is what lets
  the script be imported by a test, or promoted, without running.

```python
# WRONG — statements at module level: importing the file, from a test or a package, runs it
with Path(sys.argv[1]).open(encoding="utf-8", newline="") as source:
    count_by_status = Counter(row["status"] for row in csv.DictReader(source))
print(count_by_status)

# CORRECT — main() plus functions; importing the file runs nothing
def main() -> None:
    with Path(sys.argv[1]).open(encoding="utf-8", newline="") as source:
        count_by_status = Counter(row["status"] for row in csv.DictReader(source))
    print(count_by_status)


if __name__ == "__main__":
    main()
```

- **No layers, no packaging, no `_` prefix.** One file, no `__init__.py`, no `__all__`. The prefix
  tells an importer what is internal, and a script has no importer.
- **The standard library first.** `json` rather than `orjson`, `argparse` rather than a CLI
  framework. A dependency is worth it when it replaces real code — an HTTP client, a database
  driver — and then it is declared inline (below), never assumed installed.
- **Tests are optional.** A script is verified by running it — on a copy of the data, or in dry-run
  first. A function in it that is subtle enough to need a test is the first sign of a promotion.
- **One-line docstring for the module**: what it does and how it is run.

## What Never Relaxes

Each of these fails on exactly the run that mattered, and a script is the code most often run once
against production data:

- a timeout on every network call (`python-boundaries`);
- secrets from the environment, never in the file — scripts get pasted into chats and committed;
- `encoding="utf-8"` on every text file, `Decimal` for money, aware UTC datetimes;
- a narrow `except` and no swallowed error: a script that "finished" after silently skipping half
  the rows is worse than one that crashed;
- the failure boundary from `core.md`: one row, one file, one request — recorded, counted, and the
  count reported at the end, with a non-zero exit code when it is not zero;
- subprocess argument lists and parameterized SQL (`python-security`);
- annotated signatures — the cheapest part of a later promotion, and `mypy` still finds the
  `None` passed where a value was required.

```python
# WRONG — urlopen has no default timeout: a server that stops answering holds the script forever
with urllib.request.urlopen(export_url) as response:
    rows = response.read()

# CORRECT — even a one-off waits for a stated time, then fails and says so
with urllib.request.urlopen(export_url, timeout=TIMEOUT_SECONDS) as response:
    rows = response.read()
```

## A Script That Changes Data

The batching, bounding and idempotence of a backfill are in `python-migrations`. What a script
adds:

- **Dry run is the default; writing takes `--apply`.** The first run of a data fix is the one with
  the bug in it, and it should print what it would do.
- **Report before and after**: how many rows match, how many were changed, how many failed — and
  the identifiers of the changed ones, in a file, so the run can be audited or undone.
- **Re-runnable**: a second run after a crash changes nothing that the first one already changed.

```python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Lower-case every file name in a directory. Run: uv run lowercase_names.py DIR [--apply]."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

EXIT_SUCCESS: Final = 0
EXIT_FAILURE: Final = 1

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lower-case every file name in a directory.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--apply", action=argparse.BooleanOptionalAction, default=False)
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    renames = planned_renames(arguments.directory)
    for source, target in renames:
        print(f"{source.name} -> {target.name}")
    failed_count = apply_renames(renames) if arguments.apply else 0
    logger.info("renames planned", extra={"planned": len(renames), "failed": failed_count})
    sys.exit(EXIT_FAILURE if failed_count else EXIT_SUCCESS)


def planned_renames(directory: Path) -> list[tuple[Path, Path]]:
    renames = []
    for source in sorted(directory.iterdir()):
        target = source.with_name(source.name.lower())
        # rename() replaces an existing target without asking
        if target != source and not target.exists():
            renames.append((source, target))
    return renames


def apply_renames(renames: Sequence[tuple[Path, Path]]) -> int:
    failed_count = 0
    for source, target in renames:
        try:
            source.rename(target)
        except OSError:
            logger.exception("rename failed", extra={"source": str(source)})
            failed_count += 1
    return failed_count


if __name__ == "__main__":
    main()
```

## Inline Metadata: PEP 723 and `uv run`

A script that needs a third-party package declares it in its own header, so it runs anywhere with
one command and never against whatever happens to be installed:

- **`uv run script.py`** reads the `# /// script` block, builds an isolated environment from it and
  runs the file. `uv add --script script.py 'niquests>=3.21'` edits the block;
  `uv lock --script script.py` writes `script.py.lock` beside it, for a script that must give the
  same result when it is run again in a month.
- **Dependencies carry a lower bound**, as everywhere, and `requires-python` states the floor the
  script was written against.
- **`#!/usr/bin/env -S uv run --script`** as the first line makes the file directly executable.

## Notebooks

- **Restart and run all before the result is shared.** Cells run out of order leave state no reader
  can reproduce; a notebook whose result depends on it has no result.
- **Outputs are part of the file.** A printed token or a customer's row is committed with it; clear
  outputs that hold either before saving.
- **Code that survives the exploration moves to a module**, where the full rules apply, and the
  notebook imports it. A function copied from one notebook into the next is a module not yet
  written.
