---
paths:
  - "**/pyproject.toml"
  - "**/ruff.toml"
  - "**/.ruff.toml"
---

# ruff

Formatter and linter in one tool, configured once, with no per-developer settings and no CLI flags
that change the outcome.

## The Formatter Is the Single Source of Truth for Layout

- **Never hand-format against it**, and never disable it for a file. Layout stops being a topic the
  moment one tool decides it; re-litigating a line break is time spent on the one thing that was
  already settled.
- **Pin the version.** Formatting output changes between releases; an unpinned formatter turns an
  unrelated upgrade into a diff across the whole repository, and a review into archaeology.
- **The formatter runs before the linter**, always in that order: some findings disappear once the
  code is formatted, and fixing them by hand first is wasted work.

## Selecting Rules

- **Select broadly, then justify each exception.** A short allowlist looks tidy and quietly permits
  everything nobody thought to enable; a broad selection with a handful of reasoned ignores states
  what the project actually decided.
- **Every ignore carries a comment saying why.** An ignore without a reason cannot be re-evaluated:
  nobody knows whether the constraint that produced it still exists, so it stays forever.
- **Prefer per-file ignores to global ones.** A global ignore silences a rule everywhere because of
  a handful of files, and the rule never comes back. A named file with a reason stays visible and
  gets deleted when the reason does.

## Fixes

- **Automatic fixes are reviewed, not trusted.** The safe ones are safe by the tool's own
  classification; the ones it marks unsafe change behaviour and are applied one at a time, with the
  diff read.
- **A fix that makes a finding disappear without making the code better is not a fix.** Rewriting a
  comprehension to satisfy a rule while leaving it unreadable trades a warning for a worse line.

## Suppressions

- **Always with the rule code and the reason on the same line.** A bare suppression hides every
  future finding on that line, including the one that matters.
- **When another linter runs alongside**, declare its prefix as external so its suppressions are not
  reported as unused — otherwise the two tools spend the day disagreeing about each other's
  comments.
- **Suppression count is a metric that only goes down.** Adding one is a decision worth stating in
  the pull request.

## Where the Boundary Is

Ruff is fast and mechanical: syntax, imports, obvious bugs, style, and the security surface. What it
does not judge is structural load on a reader — cognitive complexity, how much one module carries,
how many things a class does. That is a second linter's job, and the split is deliberate; see
`wemake-python-styleguide.md`.
