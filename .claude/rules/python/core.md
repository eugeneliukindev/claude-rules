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
| `python-migrations` | a schema change, a backfill |
| `python-workers`, `python-caching` | a queue consumer or a background job; a cache in front of a database or an API |
| `python-packaging` | a package other code imports: `__all__`, facade, `_internal`, optional extras, deprecation, a module named like a stdlib one |
| `python-project`, `python-container` | a new project or package from nothing: layout, `pyproject.toml`, tool configuration; a Dockerfile, an image |
| `python-scripts` | a one-off script, a notebook, a backfill — what relaxes there and what never does |
| `python-cli` | an entry point with an argument parser |
| `python-security`, `python-auth` | input from outside: a body, a filename, a URL, a subprocess argument, a credential; a bearer token, a JWT, a session cookie, a permission or ownership check |
| `python-observability` | metrics, tracing, correlation ids, where logging is configured |
| `python-performance` | a path already measured and found slow |
| `python-examples` | an example that ships — docstring, README, `examples/` |
| `python-rules-authoring` | editing these rules or skills |
| `python-<library>` | the code imports that library — `pydantic`, `sqlalchemy`, `alembic`, `fastapi`, `strawberry`, `grpc`, `tenacity`, `niquests`, `orjson`, `pytest`, `asyncpg`, `redis`, `cashews`, `faststream`, `pyjwt` |

Style, layout and complexity belong to the formatter, the linters and the type checker, which the
project picks; **nothing here restates what a tool decides**, and where they disagree the tool wins
and this file gets a PR. Two things do belong here:

- **A suppression carries its rule code and its reason on its line**, or directly above when it
  will not fit — never wrapped away by the formatter. The count only ever ratchets down.
- **A limit is named, not raised.** One module with fifteen members must not buy every other
  module the right to fifteen: the limit stays and the file is named, with a checkable reason. When
  three files need the same escape, the rule is describing something real about the architecture.

## When Rules Conflict

1. An explicit instruction from the person you are working with, for this task.
2. A rule these files state without qualification.
3. How `pydantic` or `sqlalchemy` shape the same thing in their public API — not their internals.
4. Consistency with the surrounding code of the same package — for a *prefer*, never against (2).
5. The default (*prefer*) in these files.
6. Your own judgement — and say so, rather than letting it read as a rule.

A rule that is wrong for the situation, or regularly worked around, is changed here with the
reasoning — never worked around silently in code.

**In old code, what the task writes obeys these files; what it only passes stays as it is** —
reformatting or renaming beyond the task buries the change in its diff. A violation noticed and
left goes in the summary or the PR description, never copied into the new code.

## Principles

Five, in priority order; when two rules conflict the earlier principle wins. **Correct** — the code
does what its name and signature promise for every input the types allow, and fails loudly
otherwise. **Readable** — a teammate new to the file understands it top-down without opening
others; names carry the meaning. **Simple** — the least machinery that solves today's problem.
**Typed** — illegal states are unrepresentable; the checker catches the mistake, not the reviewer.
**Fast enough, by measurement** — algorithmic sanity always, anything more with a profile in hand.

And three properties of the system as a whole:

- **A failure stays where it happened.** One bad input or one unreachable dependency never stops
  the run: name what is protected — this row, this source, this request — and catch at exactly that
  boundary, recording the reason. Degradation has a stated direction — skip, retry later, serve
  stale, return partial — written where the code makes the choice.

  ```python
  # WRONG — the boundary is the whole loop: one unreachable SKU and nothing after it is updated
  try:
      for sku in skus:
          store.update_price(sku, supplier.fetch_price(sku))
  except SupplierError:
      logger.warning("price fetch failed", extra={"sku": sku})

  # CORRECT — the boundary is one SKU: it is recorded and skipped, the run goes on
  for sku in skus:
      try:
          price = supplier.fetch_price(sku)
      except SupplierError:
          logger.warning("price fetch failed", extra={"sku": sku})
          continue
      store.update_price(sku, price)
  ```
- **Cost grows slower than the work.** Every external collection has a limit, every fan-out a
  semaphore, every run a deadline, every cache an expiry — one without grew per request, never read.
  "It has always been small" is not a bound.
- **The next person is you, without the context.** One actor per module; a new case is data or a
  new file, never a new branch in something that already works. Deleting must be as easy as adding.

## YAGNI, KISS, DRY

- **Build what today's requirement needs.** A speculative feature costs everything that must keep it
  working; a generalisation built for one case is a guess about the second. An option nobody sets is
  a branch never known to work: a test client's flag did nothing for two majors.
- **The simplest construction that fully solves the problem**, not the shortest: the boring
  mechanism — a function over a class, a dict over a registry — judged at the point of *use*.
- **DRY is about knowledge, not text.** Identical fragments answering to different actors are not
  duplication — merged, the next change arrives as a parameter, then a flag, then a branch.
  Fragments that must change together are duplication however different they look — a limit in a
  validator and in a schema. **Wait for the third occurrence**; a shared constant often cures it.

## Definition of Done

The formatter, the linters, the strict type checker and the tests run first, in that order, each
clean with no new suppression. Then the eight checks no tool makes, skipped first under pressure —
`/python-review` runs the whole list over a diff:

- [ ] Every new identifier passes `naming.md`'s Self-Check and survives the relocation test
- [ ] Every new module and class answers to one actor — name who would ask to change it
- [ ] Every helper has a reason from `functions.md`, every class a trigger from `classes.md`
- [ ] Constants sit at the top of the module, and **every top-level name not used outside is
      prefixed** — `find_unprefixed_names.py` reports nothing new
- [ ] No generically named unit contains concrete logic; no concrete rule lives in two places
- [ ] No `Any`, magic literal or cross-layer `dict[str, Any]`; `@override` and `Final` where due
- [ ] Every conversion preserves the cause; nothing returns `None`/`False`/`-1` to signal an error;
      errors are logged once, at the boundary, with no secrets or PII
- [ ] Every comment and docstring passes the relocation test; no credential or URL is hardcoded
