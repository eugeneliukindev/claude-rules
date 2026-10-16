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

This procedure runs the eight checks `core.md` ends with. Review a diff against these files: what changed, not the whole repository, and not the code's taste.

## 1. Fix the Scope

- **Take the range the user names, or else the current branch against its merge base with main, plus uncommitted work.** Run `git diff --merge-base main -- '*.py'` and `git diff HEAD -- '*.py'`.
- **List the changed files and, in each, the changed units: the functions, classes, constants and modules the diff adds or edits.** Apply a check to a changed unit, never to its neighbours (`core.md`).

## 2. Run the Project's Checks

- **Run what the project's CI already runs, the tests included, and report each failure as a finding.** Never install a tool the project does not use.

## 3. The Checks, Unit by Unit

Ask each question of every changed unit, answered from the code, not from the description of the change; open the file that decides it when the answer is not obvious.

1. Names: every new identifier follows `naming.md` and survives the relocation test, with no history, place, caller or neighbour in the name.
2. Actors: every new module and class answers to one actor. Name who would ask to change each function; two answers are two modules (`principles.md`).
3. Reasons to exist: every new helper has a reason from `functions.md` and fails none of its inline tests; every new class has a trigger from `classes.md`.
4. Surface: constants sit at the top of the module, and every top-level name nothing outside its module uses is prefixed. Run `python scripts/find_unprefixed_names.py src` from this skill over the source package, without the tests, and report what it lists.
5. Abstraction level: no generically named unit branches on a concrete type, channel, vendor, tenant or environment, and no concrete rule lives in two places (`naming.md`).
6. Types: no `Any`, no magic literal, no `dict[str, Any]` crossing a layer; `@override` on every override, `Final` on every constant, `@final` where a class is not designed for subclassing (`types.md`); a setting a function or method reads is a keyword parameter defaulted to its module constant, outside the root, tests, framework-parsed signatures and scripts (`functions.md`).
7. Errors: every conversion keeps its cause with `raise ... from`; nothing returns `None`, `False` or `-1` for an error; every `except` is as narrow as the lines it guards; an error is logged once, where it is handled, with no secret or personal data (`errors.md`, `logging.md`).
8. Comments: every comment is one of the four forms in `comments.md` and passes the relocation test, and no credential, URL or environment value is hardcoded.

- **Read the diff against each skill it reaches.** An outbound call, a file or a payload against `python-boundaries`; outside input or an access check against `python-security`; a settings field or an entry point against `python-wiring`; a contract or a fake against `python-contracts`; a test file against `testing.md`.
- **Read a call into a library against its current documentation, never from memory.**

## 4. Report

- **Write one finding per defect, most severe first.** A wrong result or a lost error comes before a name.
- **Give each finding its location, rule, defect and fix: `path:line - rule file or skill: what is wrong, in one sentence. The change that fixes it.`** A finding with no rule behind it is an opinion: label it so, or leave it out.
- **Report a clean review as a result.** Say which steps ran and that they were clean, and never pad the list.
- **List a violation in untouched code apart, under its own heading, and do not fix it.** It belongs to another change.
- **Report a step that could not run, with the reason.** A missing tool or tests needing a database is never skipped silently.
- **When asked to fix as well, fix the findings in the diff, rerun step 2, and report what changed.**
