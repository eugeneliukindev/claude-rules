# A Script That Changes Data

## Contents

- Dry run by default, writing behind `--apply`
- A journal of every change
- A second run changes nothing the first one changed
- A replay republishes under the original event ids
- The complete script

The batching, bounding and idempotence of a backfill against a live database are in
`python-migrations`; this file is what a script adds.

### Dry run is the default, and writing takes `--apply`

**Why:** the first run of a data fix is the one with the bug in it; it should print what it would
do, and the counts it would reach, before anything is written.

**Example:**
```python
# WRONG — the first run writes, so the bug in it is found in the data
def main() -> None:
    parser = argparse.ArgumentParser(description="Lower-case every file name in a directory.")
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    renames, _skipped_count = planned_renames(arguments.directory)
    apply_renames(renames, journal=sys.stdout)


# CORRECT — the plan is printed; only --apply writes
def main() -> None:
    parser = argparse.ArgumentParser(description="Lower-case every file name in a directory.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--apply", action=argparse.BooleanOptionalAction, default=False)
    arguments = parser.parse_args()
    renames, _skipped_count = planned_renames(arguments.directory)
    for source, target in renames:
        print(f"{source.name} -> {target.name}")
    if arguments.apply:
        apply_renames(renames, journal=sys.stdout)
```

### Every change is written to a journal as it is made

**Why:** a count says how much changed, not what; the identifiers of the changed items, one line
each, let the run be audited or undone. Written as each change succeeds, the journal is right even
when the run dies halfway.

**Example:**
```python
# WRONG — the failures are counted, and nothing records which files were renamed
def apply_renames(renames: Sequence[tuple[Path, Path]]) -> int:
    failed_count = 0
    for source, target in renames:
        try:
            source.rename(target)
        except OSError:
            logger.exception("rename failed: %s", source.name)
            failed_count += 1
    return failed_count


# CORRECT — each rename that succeeded is a line in the journal, written as it happens
def apply_renames(renames: Sequence[tuple[Path, Path]], *, journal: TextIO) -> int:
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

### A second run after a crash changes nothing the first one changed

**Why:** a data fix is re-run after every crash, timeout or interrupted session; an update relative
to the current value applies twice to the rows the first run reached. Each row records the fix it
received, and the update skips the rows that carry it.

**Example:**
```python
# WRONG — re-run after a crash, every fee the first run reached is raised again
def raise_monthly_fees(*, connection: sqlite3.Connection, percent: int) -> int:
    with connection:
        cursor = connection.execute(
            "UPDATE plan SET monthly_fee_cents = monthly_fee_cents * (100 + ?) / 100",
            (percent,),
        )
    return cursor.rowcount


# CORRECT — each row is marked with the fix; a second run changes only what the first did not
def raise_monthly_fees(*, connection: sqlite3.Connection, percent: int, fix_id: str) -> int:
    with connection:
        cursor = connection.execute(
            "UPDATE plan SET monthly_fee_cents = monthly_fee_cents * (100 + ?) / 100,"
            " last_fix_id = ? WHERE last_fix_id IS NOT ?",
            (percent, fix_id, fix_id),
        )
    return cursor.rowcount
```

### A replay of dead-lettered messages republishes each under its original event id

**Why:** some of the dead-lettered messages went through on a retry before they were parked; under a
new id the consumers' idempotency cannot recognise them, and they are applied twice
(`python-workers`).

**Example:**
```python
# WRONG — a new id: every consumer that already applied the event applies it again
def replay_dead_letters(*, dead_letters: DeadLetterStore, publisher: EventPublisher) -> int:
    replayed_count = 0
    for dead_letter in dead_letters.pending():
        publisher.publish(Event(event_id=uuid.uuid4(), payload=dead_letter.payload))
        replayed_count += 1
    return replayed_count


# CORRECT — the original id, which the consumers' idempotency already knows
def replay_dead_letters(*, dead_letters: DeadLetterStore, publisher: EventPublisher) -> int:
    replayed_count = 0
    for dead_letter in dead_letters.pending():
        publisher.publish(Event(event_id=dead_letter.event_id, payload=dead_letter.payload))
        replayed_count += 1
    return replayed_count
```

## The Complete Script

Dry run by default, the plan printed, a journal on `--apply`, the counts on stderr, and a non-zero
exit when anything was skipped or failed.

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
from typing import Final, TextIO

EXIT_SUCCESS: Final = 0
EXIT_FAILURE: Final = 1

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lower-case every file name in a directory.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--apply", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--journal", type=Path, default=Path("renames.tsv"))
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    renames, skipped_count = planned_renames(arguments.directory)
    for source, target in renames:
        print(f"{source.name} -> {target.name}")
    failed_count = 0
    if arguments.apply:
        with arguments.journal.open("a", encoding="utf-8") as journal:
            failed_count = apply_renames(renames, journal=journal)
    verb = "renamed" if arguments.apply else "would rename"
    print(
        f"{verb} {len(renames) - failed_count} of {len(renames)}, "
        f"{skipped_count} skipped, {failed_count} failed",
        file=sys.stderr,
    )
    sys.exit(EXIT_FAILURE if failed_count or skipped_count else EXIT_SUCCESS)


def planned_renames(directory: Path) -> tuple[list[tuple[Path, Path]], int]:
    renames = []
    skipped_count = 0
    for source in sorted(directory.iterdir()):
        target = source.with_name(source.name.lower())
        if target == source:
            continue
        # rename() replaces an existing target without asking
        if target.exists():
            logger.warning("target exists, skipped: %s", source.name)
            skipped_count += 1
            continue
        renames.append((source, target))
    return renames, skipped_count


def apply_renames(renames: Sequence[tuple[Path, Path]], *, journal: TextIO) -> int:
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
