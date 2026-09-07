---
paths:
  - "**/setup.cfg"
  - "**/.flake8"
  - "**/tox.ini"
---

# wemake-python-styleguide

A second linter, running on `flake8`, kept for what the first one does not measure. Its
configuration lives in a `flake8` section, because that is the plugin host — there is no separate
config file to look for.

## Why Two Linters

The split is deliberate, not historical debt:

- **`ruff` judges the code.** Syntax, imports, likely bugs, style, the security surface — mechanical
  properties of a line or a statement, decided fast.
- **This one judges the load on the reader.** Cognitive complexity, Jones complexity, how many
  methods a class carries, how many names a module imports, how much one function holds. These are
  the checks that say "a person cannot keep this in their head", which no formatter and no
  fast-path linter attempts.

Keep the selection narrow — its own prefix only. `flake8`'s built-in checks overlap `ruff`
completely, and running both means two tools reporting the same finding with different numbers.

## Limits Are Named, Not Raised

- **Raising a global limit silences it everywhere.** One module with fifteen members should not
  buy every other module the right to have fifteen. The limit stays; the file is named.
- **Every per-file exception carries a reason.** "This enum lists every value in the world",
  "this is the composition root and exists to bring everything together" — a reason that can be
  checked later, and that stops applying when the file changes.
- **A per-file exception that nobody can justify is a design finding**, not a configuration
  problem. If three files need the same escape, the rule is describing something real about the
  architecture.

## One Global Exception Is Sometimes Right

A limit calibrated for a shorter line does not fit a longer one: more fits on a line, so more nodes
land on it, and a per-line complexity ceiling fires on code that is not actually dense. Adjusting
that once, globally, with the arithmetic written down, is honest. Adjusting it because a few files
fail is not.

## Suppressions

- **Inline suppressions use its own prefix**, and the other linter must be told that prefix is
  external — otherwise it reports the comment as an unused suppression, and removing it breaks this
  linter instead.
- Same discipline as everywhere: the code, and the reason, on the same line.

## Configuration

It has no config file of its own — the settings live in the `flake8` section, usually `setup.cfg`:

```ini
[flake8]
# Its own prefix and syntax errors only: flake8's built-in checks overlap ruff completely,
# and running both means two tools reporting one finding with different numbers.
select = WPS, E99

# Docstring examples are code, and they are executed.
doctests = true

# The one global adjustment worth making, with the arithmetic written down: the default
# ceiling assumes an 80-character line. At 120 roughly half again as many nodes fit on
# one line, so the per-line limit fires on code that is not actually dense.
max-line-complexity = 21

ignore =
  # Argument count is ruff's job — PLR0913, configured with max-args in pyproject.toml.
  WPS211

# Per-file exceptions carry a reason each, and the reason can stop being true.
per-file-ignores =
  # An enum lists every value in the world; the count is the domain's, not the module's.
  */enums.py: WPS202
  # The composition root exists precisely to bring everything together in one place.
  */app.py: WPS201
```
