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

The rules in this directory are for code that lives; never grow a forty-line one-off a contract, a fake and a composition root. A script is a file run by hand or by one person's one-off job, imported by nothing and read by its author: a data fix, a report, a backfill, a notebook. Still verify a token it acts on, and still batch and bound a backfill against a live table.

## When a Script Stops Being One

- **Apply every rule from the next edit on, once the file is imported, scheduled, run by others, or outgrows a screen.** The signals: something imports it or copies a function out of it, it runs on a schedule or in production with nobody watching, someone other than its author is expected to run it, or `main()` no longer fits on a screen, a few hundred lines in all.
- **Promote a script by moving it, not rewriting it.** The functions go into a package, and the contracts, fakes and tests arrive with the second implementation or the first test, as anywhere.

## What Relaxes

- **Call the one implementation directly: no contract, no fake, no composition root.** Fakes (`testing.md`), layers, `__init__.py`, `__all__` and the `_` prefix (`modules.md`) are ceremony in a file nobody imports.
- **Read constants where the function stands.** The defaulted setting of `functions.md` is for code a test calls.
- **Verify a script by running it, on a copy of the data or dry-run first.** A function subtle enough to need a test is the first sign of a promotion.
- **Say in a one-line module docstring what the script does and how it is run.**
- **Keep the statements in `main()` and functions, never at module level (`modules.md`).** `main()` builds what it needs, the connection or the client, and uses it inside a `with`, so a test can import the file and a promotion does not run it.
- **Reach for the standard library first, and add a package only to replace real code.** A spreadsheet writer or a database driver earns its place, `orjson` for `json` does not.
- **Declare every other package in the script's PEP 723 header.** It then runs anywhere with one command, never against whatever is installed: `uv run script.py` builds an isolated environment from the block, `uv add --script` edits it, and `uv lock --script` pins a script that must give the same result in a month.
- **Make the script executable with `#!/usr/bin/env -S uv run --script` as its first line.**
- **Log plain text under `basicConfig`, and put what the reader must see in the message, not in `extra=`.** The `basicConfig` format prints no `extra=` field, so a skipped item's identifier passed there never reaches the terminal.
- **Print the counts the reader must see to stderr at the end.**

## What Never Relaxes

These fail on the run that mattered; a script is the code most often run once against production data.

- **Give every network call a timeout.**
- **Read secrets from the environment.** Scripts get pasted and committed.
- **Open every text file with `encoding="utf-8"`, keep money in `Decimal`, and keep datetimes aware and in UTC.**
- **Catch narrowly (`errors.md`).** A run that "finished" skipping half the rows is worse than a crash.
- **Count each failed item (`principles.md`), and exit non-zero when any item was skipped or failed.**
- **Pass subprocess arguments as a list, and parameterize SQL.**
- **Give a shared-cache key a TTL, and never pickle into it.**
- **Annotate signatures (`types.md`).**

## A Script That Changes Data

- **Make a dry run the default, and write only with `--apply`.** The first run of a data fix is the one with the bug in it; print what it would do and the counts it would reach before anything is written.
- **Write every change to a journal as it is made, one line of identifiers per changed item.** A count says how much changed, not what; the journal lets the run be audited or undone, and written as each change succeeds it is right even when the run dies halfway.

## Notebooks

- **Restart a notebook and run it top to bottom before sharing its result.** Cells run out of order leave state no reader can reproduce; run it headless from a clean kernel as the check.
- **Clear outputs that hold a token or a customer's row before committing the notebook.** Outputs are part of the `.ipynb` file and stay in the history after the cell is fixed.
- **Move code that survives the exploration into a module the notebook imports.** A function copied from notebook to notebook drifts in each copy; in a module the full rules apply, and it can be tested.
