---
paths:
  - "**/*.py"
---

# Python — Modules

## Module Layout and Encapsulation

Every module has the same order, so a reader always knows where to look:

1. Module docstring — one line, always.
2. `from __future__ import annotations`, when the target version needs it.
3. Imports.
4. `__all__` — in `__init__.py` only, and there it is the whole file.
5. **Module-level constants.**
6. Type aliases, `NewType`s, type parameters.
7. Module logger.
8. Exception classes.
9. Contract-ABCs and protocols, then concrete classes, then the models private to this module.
10. Public functions, high-level first — the step-down rule applies to modules as to classes.
11. Private functions, in call order.
12. The `__main__` guard — a single call to `main()`, nothing else.

**Where Python's definition order overrides this one, it wins** — a validator comes before the
type alias built from it. Anything else that will not fit is a seam: a constant derived from a class
means the module holds the shape and what is computed from it, so **split it** rather than
renumber the list.

- **Size is a smell, not a limit.** The linters enforce a ceiling; the seam is your judgement.
- **No executable statements at import time** other than constants and the logger. No network
  calls, no file reads, no settings construction — these make imports slow, order-dependent and
  untestable. **`main()` is a function, never module-level code.**

## Every Top-Level Name Not Used Outside Takes an Underscore

Classes, functions, constants and type aliases alike. A settings section that only appears as a
field of the root, a row shape only its own repository builds, a policy only its own service
applies, a limit only its own function reads, an alias only its own signatures mention: each takes
the prefix — `_RetrySettings`, `_OrderRow`, `_RefundPolicy`, `_MAX_BATCH_ROWS`, `_Headers`. Without
it the name reads as part of the module's surface, and the first import from another module makes it
one for good.
**Constants and aliases are the ones that get missed**: a class draws attention once imported, a
constant is quietly read from a second module and ends up with two homes and no owner.

The test is mechanical: for each top-level name, search the tree without the file that defines
it, and prefix everything with no hits. A script does it:
`python ~/.claude/skills/python-packaging/scripts/find_unprefixed_names.py ROOT`. Run it **after**
the move that made a name internal — that is when a public name quietly stops being one. A name a
framework reaches through a decorator — a CLI command, a route handler, a fixture — has a caller
the search cannot see; the script lists those separately, and exempts `main`, `run` and `logger`.

## Imports

- **Import modules for modules, names for classes and functions.** Then call `invoices.issue(...)`
  or `issue_invoice(...)` — never a three-level attribute chain, which hides what is used.
- **A function-level import is flagged, and exactly three reasons buy the suppression**: breaking a
  genuine circular import, loading a heavy or optional implementation on demand, and a façade that
  exports implementations whose libraries are separate extras. Each carries the reason on the line.
  Generic "lazy loading" is not one of them — restructure instead.
- **Annotations that would create a cycle or pull a heavy dependency go under `TYPE_CHECKING`.**
- **Never depend transitively on something you import**; every direct dependency is declared, with
  a lower bound. **Never feature-detect with `try: import x`** in application code.

## Resources

- **Anything acquired is released by a context manager** — files, locks, sessions, transactions,
  clients. Writing one, `ExitStack` for a dynamic number, and what cleanup may raise: the
  `python-wiring` skill, which also owns who closes what.
