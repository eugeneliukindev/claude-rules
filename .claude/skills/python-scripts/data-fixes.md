# A Script That Changes Data

### Dry run is the default, and writing takes `--apply`

**Why:** the first run of a data fix is the one with the bug in it; it should print what it would
do, and the counts it would reach, before anything is written.

**Example:**
```python
# WRONG — the first run writes, so the bug in it is found in the data
def main() -> None:
    parser = argparse.ArgumentParser(description="Strip the hyphens from cover scan names.")
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    renames, _skipped_count = planned_cover_renames(arguments.directory)
    apply_cover_renames(renames, journal=sys.stdout)


# CORRECT — the plan is printed; only --apply writes
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
# WRONG — the failures are counted, and nothing records which scans were renamed
def apply_cover_renames(renames: Sequence[tuple[Path, Path]]) -> int:
    failed_count = 0
    for source, target in renames:
        try:
            source.rename(target)
        except OSError:
            logger.exception("rename failed: %s", source.name)
            failed_count += 1
    return failed_count


# CORRECT — each rename that succeeded is a line in the journal, written as it happens
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
