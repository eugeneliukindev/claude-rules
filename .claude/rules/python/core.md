---
paths:
  - "**/*.py"
---

# Python — Core

Every Python edit loads this directory, tests also `testing.md`; everything else is a skill:

| Skill | When |
|---|---|
| `python-types` | choosing between `Literal`/`Enum`/`NewType`/`TypedDict`/a value object, replacing a `dict[str, Any]`, writing a generic or a typed decorator, narrowing an unknown, reaching for `collections.abc` |
| `python-contracts` | an ABC or `Protocol`, a subclass or mixin, what a consumer is handed, a second implementation, a test fake, where implementations live |
| `python-wiring` | an entry point or an application factory, where an object is built, opening a pool or a client, a settings field or a constant, removing a global |
| `python-boundaries` | HTTP, queues, caches, files, serialization, validation at the edge, timeouts, retries, idempotency, time, money, identifiers |
| `python-security` | input from outside: a body, a filename, a URL, an upload, a subprocess argument, a credential; a bearer token, a JWT, a session cookie, a permission or ownership check |
| `python-scripts` | a one-off script, a notebook, a backfill or data fix — what relaxes there |
| `python-review`, `python-rules-authoring` | reviewing a diff against these rules; editing these rules or skills |

The principles and YAGNI, KISS and DRY are in `principles.md`.

## The Tools Decide Style

### Nothing here restates what a tool decides; where they disagree, the tool wins

**Why:** style, layout and complexity belong to the formatter, the linters and the type checker the
project picks; a rule that restates one drifts from it. They already hold: `mypy --strict` and
ruff's `UP` (every annotation, the modern spelling), `ANN401` (no `Any`), `FBT` (no positional
boolean), `PLC0415` (an import inside a function), `TC` (an annotation-only import under
`TYPE_CHECKING`), `ERA001` (commented-out code), `G004` (a formatted log message), `PT011` (a
`pytest.raises` too broad).

### A suppression carries its rule code and its reason on its line

**Why:** a bare `# type: ignore` or `# noqa` hides every future error on that line too, and nobody
can tell whether it is still needed; the count only ratchets down.
**Except:** directly above the line, when the reason will not fit.

### A limit is named, not raised

**Why:** one module with fifteen members must not buy every other module the right to fifteen; the
limit stays and the file is named, with a checkable reason.

## When Rules Conflict

1. An explicit instruction from the person you are working with, for this task — about *how* the
   code is written. A requirement says *what* it does — "production uses this URL" — and is met
   the way these files say: each difference a setting, never a branch on the environment's name.
2. A rule these files state without qualification.
3. Consistency with the surrounding code of the same package — for a *prefer*, never against (2).
4. How `pydantic` or `sqlalchemy` shape the same thing in their public API — not their internals.
5. The default (*prefer*) in these files.
6. Your own judgement — and say so, rather than letting it read as a rule.

### In old code, what the task writes obeys these files; what it only passes stays as it is

**Why:** reformatting or renaming beyond the task buries the change in its diff. A violation noticed
and left goes in the summary or the PR description, never copied into the new code.

## Definition of Done

The formatter, the linters, the strict type checker and the tests run first, in that order, each
clean with no new suppression. Then the eight checks no tool makes, skipped first under pressure —
`/python-review` runs the whole list over a diff:

- [ ] Every new identifier follows `naming.md` and survives the relocation test
- [ ] Every new module and class answers to one actor — name who would ask to change it
- [ ] Every helper has a reason from `functions.md`, every class a trigger from `classes.md`
- [ ] **Every name used only inside its module or class is prefixed** with an underscore
- [ ] No generically named unit contains concrete logic; no concrete rule lives in two places
- [ ] `@override`, `@final` and `Final` where due; a setting is a keyword parameter defaulted to its
      constant
- [ ] Every conversion keeps its cause with `from`; nothing returns `None` or `False` for an error;
      a failure is logged once, where it is handled, with no secret or personal data
- [ ] Every comment is one of the four forms in `comments.md` and passes the relocation test
