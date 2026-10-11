---
paths:
  - "**/*.py"
---

# Python — Core

Every Python edit loads this directory, tests also `testing.md`; everything else is a skill:

| Skill | When |
|---|---|
| `python-types` | choosing between `Literal`/`Enum`/`NewType`/`TypedDict`, writing a generic, narrowing an unknown, reaching for `collections.abc`, a dunder |
| `python-boundaries` | HTTP, queues, caches, files, serialization, timeouts, retries, time, money, identifiers |
| `python-wiring` | an entry point, where an object is built, a resource's lifetime, a settings field |
| `python-layers` | which layer may import which, an import-linter contract |
| `python-contracts`, `python-metaclasses` | an ABC or `Protocol`, a second implementation, a test fake, where implementations live; a metaclass, `__init_subclass__`, a descriptor, a subclass registry |
| `python-async`, `python-streaming` | `async def`, threads, processes; an SSE or WebSocket endpoint, a streamed response |
| `python-persistence` | a transaction boundary, a repository |
| `python-migrations` | a schema change, planning a backfill |
| `python-workers`, `python-caching` | a queue consumer or a background job; a cache in front of a database or an API |
| `python-packaging` | a package other code imports: `__all__`, facade, `_internal`, optional extras, deprecation, a module named like a stdlib one |
| `python-project`, `python-container` | a new project or package from nothing: layout, `pyproject.toml`, tool configuration; a Dockerfile, an image |
| `python-scripts` | a one-off script, a notebook, the backfill script itself — what relaxes there |
| `python-cli` | an entry point with an argument parser |
| `python-security`, `python-auth` | input from outside: a body, a filename, a URL, a subprocess argument, a credential; a bearer token, a JWT, a session cookie, a permission or ownership check |
| `python-observability` | metrics, tracing, correlation ids, where logging is configured |
| `python-performance` | a path already measured and found slow |
| `python-examples` | an example that ships — docstring, README, `examples/` |
| `python-rules-authoring` | editing these rules or skills |
| `python-<library>` | the code imports that library — `pydantic`, `sqlalchemy`, `alembic`, `fastapi`, `strawberry`, `grpc`, `tenacity`, `niquests`, `orjson`, `pytest`, `asyncpg`, `redis`, `cashews`, `faststream`, `pyjwt` |

The principles and YAGNI, KISS and DRY are in `principles.md`.

## The Tools Decide Style

### Nothing here restates what a tool decides; where they disagree, the tool wins

**Why:** style, layout and complexity belong to the formatter, the linters and the type checker the
project picks; a rule that restates one drifts from it, and the disagreement is fixed here. Code
laid out by hand against the formatter is undone on its next run, in someone else's diff.

**Example:**
```python
# WRONG — aligned by hand: the formatter rewrites it, and the next diff carries the noise
_RETRY_DELAYS_SECONDS: Final = (0.5,   1.0,   2.0,   4.0)
_MAX_ATTEMPTS: Final         = 4


# CORRECT — the formatter's layout, left as it writes it
_RETRY_DELAYS_SECONDS: Final = (0.5, 1.0, 2.0, 4.0)
_MAX_ATTEMPTS: Final = 4
```

### A suppression carries its rule code and its reason on its line

**Why:** a bare `# type: ignore` or `# noqa` hides every future error on that line too, and nobody
can tell whether it is still needed; the count only ratchets down.
**Except:** directly above the line, when the reason will not fit — never wrapped away by the
formatter.

**Example:**
```python
# WRONG — what is ignored, and why?
payload = json.loads(body)  # type: ignore


# CORRECT — the code and the reason
payload = legacy_decoder.decode(body)  # type: ignore[no-untyped-call]  # vendored, untyped until v4
```

### A limit is named, not raised

**Why:** one module with fifteen members must not buy every other module the right to fifteen; the
limit stays and the file is named, with a checkable reason. When three files need the same escape,
the rule is describing something real about the architecture.

**Example:**
```toml
# WRONG — raised for the whole project because one module needed it
[tool.ruff.lint.pylint]
max-args = 12


# CORRECT — the limit stays; the one file is named, with its reason
[tool.ruff.lint.per-file-ignores]
"src/billing/export/columns.py" = ["PLR0913"]  # one column per CSV field, fixed by the tax format
```

## When Rules Conflict

1. An explicit instruction from the person you are working with, for this task.
2. A rule these files state without qualification.
3. Consistency with the surrounding code of the same package — for a *prefer*, never against (2).
4. How `pydantic` or `sqlalchemy` shape the same thing in their public API — not their internals.
5. The default (*prefer*) in these files.
6. Your own judgement — and say so, rather than letting it read as a rule.

A rule that is wrong for the situation, or regularly worked around, is changed here with the
reasoning — never worked around silently in code.

### In old code, what the task writes obeys these files; what it only passes stays as it is

**Why:** reformatting or renaming beyond the task buries the change in its diff. A violation noticed
and left goes in the summary or the PR description, never copied into the new code.

**Example:**
```python
# WRONG — the fix to one rounding bug arrives with a renamed module-wide helper and a reflow
def total_due(inv: Inv) -> Decimal:
    return sum((line.amount for line in inv.lines), start=Decimal(0)).quantize(_CENT)


# CORRECT — the new function follows the rules; the old neighbours are listed in the PR instead
def total_due(invoice: Invoice) -> Decimal:
    subtotal = sum((line.amount for line in invoice.lines), start=Decimal(0))
    return subtotal.quantize(_CENT, ROUND_HALF_EVEN)
```

## Definition of Done

The formatter, the linters, the strict type checker and the tests run first, in that order, each
clean with no new suppression. Then the eight checks no tool makes, skipped first under pressure —
`/python-review` runs the whole list over a diff:

- [ ] Every new identifier passes `naming.md`'s Self-Check and survives the relocation test
- [ ] Every new module and class answers to one actor — name who would ask to change it
- [ ] Every helper has a reason from `functions.md`, every class a trigger from `classes.md`
- [ ] Constants sit at the top of the module, and **every name used only inside its module or
      class is prefixed** — `find_unprefixed_names.py` reports nothing new
- [ ] No generically named unit contains concrete logic; no concrete rule lives in two places
- [ ] No `Any`, magic literal or cross-layer `dict[str, Any]`; `@override` and `Final` where due
- [ ] Every conversion preserves the cause; nothing returns `None`/`False`/`-1` to signal an error;
      errors are logged once, at the boundary, with no secrets or PII
- [ ] Every comment and docstring passes the relocation test; no credential or URL is hardcoded
