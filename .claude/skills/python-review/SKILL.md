---
name: python-review
description: >-
  Reviews Python changes against these rules: the project's checks first, then the Definition of Done checks
  per changed unit, reported as findings. ALWAYS invoke this skill when asked to review Python code,
  a diff, a branch or a pull request, or to check that Python work is done. Do not review Python
  changes directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Reviewing Python Changes

`core.md` ends with eight checks, and they are skipped first under pressure. This is
the procedure that runs them. It reviews a **diff**: what changed, against these files — not the
whole repository, and not the code's taste.

## 1. Fix the Scope

Take the range the user names; otherwise the current branch against its merge base with the main
branch, plus uncommitted work:

```bash
git diff --merge-base main -- '*.py'
git diff HEAD -- '*.py'
```

List the changed files and, in each, the changed **units** — the functions, classes, constants and
modules the diff adds or edits. A check below applies to a changed unit, never to its neighbours
(`core.md`: what the task writes obeys the rules, what it only passes stays as it is).

## 2. Run the Project's Checks

Run what the project's CI already runs, the tests included; do not install a tool the project does
not use. Each failure is a finding.

## 3. The Checks, Unit by Unit

For every changed unit, each question below, answered from the code and not from the description
of the change. Each question names the file whose rule decides it; open that file when the answer
is not obvious.

1. **Names** — every new identifier follows `naming.md` and survives the
   relocation test: no history, place, caller or neighbour in the name.
2. **Actors** — every new module and class answers to one actor. Name who would ask to change each
   function; two answers are two modules (`principles.md`).
3. **Reasons to exist** — every new helper has a reason from `functions.md` and fails
   none of the shallow-helper tests; every new class has a trigger from `classes.md`.
4. **Surface** — constants at the top of the module; every top-level name used by nothing outside
   its module is prefixed — run `python scripts/find_unprefixed_names.py .` from this skill over the
   project root, so the tests count as callers, and report what it lists.
5. **Abstraction level** — no generically named unit branches on a concrete type, channel, vendor,
   tenant or environment; no concrete rule lives in two places (`naming.md`).
6. **Types** — no `Any`, no magic literal, no `dict[str, Any]` crossing a layer; `@override` on
   every override, `Final` on every constant, `@final` where a class is not designed for
   subclassing (`types.md`); a setting a function or a method reads is a keyword parameter
   defaulted to its module constant, outside the root, tests, framework-parsed signatures and
   scripts (`functions.md`).
7. **Errors** — every conversion keeps its cause with `raise … from`; nothing returns `None`,
   `False` or `-1` to signal an error; every `except` is as narrow as the lines it guards; errors
   are logged once, at the boundary, with no secrets or PII (`errors.md`, `logging.md`).
8. **Comments** — every comment is one of the four forms in `comments.md` and passes the relocation
   test; no credential, URL or environment value is hardcoded.

Then the skills the diff reaches: an outbound call, a file or a payload against
`python-boundaries`, outside input or an access check against `python-security`, a settings field
or an entry point against `python-wiring`, a contract
or a fake against `python-contracts`. A call into a library is read against that library's current
documentation, not from memory. A test file is read against `testing.md`.

## 4. Report

One finding per defect, most severe first — a wrong result or a lost error before a name:

```text
src/shop/orders.py:42 — errors.md: `except Exception` around the whole loop swallows the cause
  and stops every later order. Narrow it to `SupplierError` around the fetch and continue per order.
```

- **Location, rule, defect, fix** — the file and line, the rule file or skill that decides it, what
  is wrong in one sentence, and the change that fixes it. A finding without a rule behind it is an
  opinion: label it so, or leave it out.
- **Nothing found is a result.** Say which steps ran and that they were clean; never pad the list.
- **Untouched code is listed apart**, under its own heading, and not fixed: a violation the diff
  did not introduce belongs to another change.
- **A step that could not run is reported**, with the reason — a tool missing, tests needing a
  database — never silently skipped.

When asked to fix as well, fix the findings in the diff, rerun step 2, and report what changed.
