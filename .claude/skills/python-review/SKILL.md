---
name: python-review
description: >-
  A procedure for reviewing Python changes against these rules: the project's own formatter,
  linters, type checker and tests first, then find_unprefixed_names.py, then the eight Definition
  of Done checks from core.md applied to every changed unit of the diff, reported as findings with
  a location, the rule and the fix — and violations in untouched code listed apart. Use when asked
  to review Python code, a diff, a branch or a pull request, or to check that Python work is done,
  or when invoked as /python-review.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Reviewing Python Changes

`core.md` ends with eight checks no tool makes, and they are skipped first under pressure. This is
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

## 2. Run the Tools the Project Runs

Which tools a project runs is its own business: read `pyproject.toml`, the pre-commit
configuration, the CI workflow or the task runner, and run what they run, in this order — the
formatter in check mode, the linters, the type checker, the tests. Do not install a tool the
project does not use, and do not substitute your own configuration for its.

Each failure is a finding. A new suppression in the diff — `# noqa`, `# type: ignore`, a
per-file ignore, a raised limit — is a finding unless it carries its rule code and reason on its
line (`core.md`).

## 3. Run the Scripted Check

For every package root the diff touches:

```bash
python <python-packaging skill's directory>/scripts/find_unprefixed_names.py src/yourpackage
```

A reported name that the diff introduced or moved is a finding; a reported name the diff did not
touch goes to the untouched list (step 5).

## 4. The Eight Checks, Unit by Unit

For every changed unit, each question below, answered from the code and not from the description
of the change. Each question names the file whose rule decides it; open that file when the answer
is not obvious.

1. **Names** — every new identifier passes the Self-Check in `naming.md` and survives the
   relocation test: no history, place, caller or neighbour in the name.
2. **Actors** — every new module and class answers to one actor. Name who would ask to change each
   function; two answers are two modules (`classes.md`).
3. **Reasons to exist** — every new helper has one of the six reasons in `functions.md` and fails
   none of the shallow-helper tests; every new class has a trigger from `classes.md`.
4. **Surface** — constants at the top of the module; every top-level name used by nothing outside
   its module is prefixed (step 3 has the evidence).
5. **Abstraction level** — no generically named unit branches on a concrete type, channel, vendor,
   tenant or environment; no concrete rule lives in two places (`naming.md`).
6. **Types** — no `Any`, no magic literal, no `dict[str, Any]` crossing a layer; `@override` on
   every override, `Final` on every constant, `@final` where a class is not designed for
   subclassing (`types.md`).
7. **Errors** — every conversion keeps its cause with `raise … from`; nothing returns `None`,
   `False` or `-1` to signal an error; every `except` is as narrow as the lines it guards; errors
   are logged once, at the boundary, with no secrets or PII (`errors.md`, `logging.md`).
8. **Comments** — every comment is one of the four forms in `comments.md` and passes the relocation
   test; no credential, URL or environment value is hardcoded.

Then the skills the diff reaches: an `async def` is read against `python-async`, a query against
`python-persistence`, a migration against `python-migrations`, an outbound call against
`python-boundaries`, a settings field against `python-wiring`, an import of a library against
its `python-<library>` skill. A test file is read against `testing.md`.

## 5. Report

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

When asked to fix as well, fix the findings in the diff, rerun steps 2–3, and report what changed.
