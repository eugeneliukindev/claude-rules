---
paths:
  - "**/*.py"
---

# Python — Core

What applies to every Python edit, one topic per file in this directory, all loaded together;
`testing.md` loads in test files. Everything else is a skill, invoked when the work reaches it — by
its own description, or by name:

| Skill | When |
|---|---|
| `python-types` | choosing between `Literal`/`Enum`/`NewType`/`TypedDict`, writing a generic, narrowing an unknown, reaching for `collections.abc`, a dunder |
| `python-boundaries` | HTTP, queues, caches, serialization, timeouts, retries, time, money, identifiers |
| `python-wiring` | an entry point, where an object is built, a settings field, a layer argument |
| `python-contracts` | an ABC or `Protocol`, a second implementation, a test fake, where implementations live |
| `python-async` | `async def`, threads, processes |
| `python-persistence` | a transaction boundary, a repository, a migration plan |
| `python-packaging` | a package other code imports: `__all__`, facade, `_internal`, optional extras, deprecation, a module named like a stdlib one |
| `python-cli` | an entry point with an argument parser |
| `python-security` | input from outside: a body, a filename, a URL, a subprocess argument, a credential |
| `python-performance` | a path already measured and found slow |
| `python-examples` | an example that ships — docstring, README, `examples/` |
| `python-rules-authoring` | editing these rules or skills |
| `python-<library>` | the code imports that library — `pydantic`, `sqlalchemy`, `tenacity`, `niquests`, `orjson` |

Style, layout and mechanical complexity belong to the formatter, the linters and the type checker.
**Nothing here restates what a tool decides**, and which tools a project runs is the project's
business. When a tool and these files disagree, the tool wins and the file gets a PR. Two things
about living with those tools do belong here:

- **A suppression carries its rule code and its reason on its line**, or directly above when it
  will not fit — never wrapped away by the formatter. The count only ever ratchets down.
- **A limit is named, not raised.** One module with fifteen members must not buy every other
  module the right to fifteen: the limit stays and the file is named, with a checkable reason. When
  three files need the same escape, the rule is describing something real about the architecture.

## When Rules Conflict

1. An explicit instruction from the person you are working with, for this task.
2. A rule these files state without qualification.
3. What `pydantic` or `sqlalchemy` does in the same situation — they are large, long-lived, and
   have paid for their choices.
4. Consistency with the surrounding code of the same package.
5. The default (*prefer*) in these files.
6. Your own judgement — and say so, rather than letting it read as a rule.

A rule that is wrong for the situation, or regularly worked around, is changed here with the
reasoning — never worked around silently in code.

## Principles

Five, in priority order; when two rules conflict the earlier principle wins. **Correct** — the code
does what its name and signature promise, for every input the types allow, and fails loudly
otherwise. **Readable** — a teammate who has never seen the file understands it top-down without
opening other files; names carry the meaning, comments are the exception. **Simple** — the least
machinery that solves today's problem. **Typed** — illegal states are unrepresentable, and the
checker catches the mistake rather than the reviewer. **Fast enough, by measurement** — algorithmic
sanity always, anything beyond that with a profile in hand.

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
- **Cost grows slower than the work.** Nothing unbounded: every external collection has a limit,
  every fan-out a semaphore, every run a deadline. Stream what can be streamed. "It has always been
  small" is not a bound.
- **The next person is you, without the context.** One actor per module; a new case is data or a
  new file, never a new branch in something that already works. Deleting must be as easy as adding.

## YAGNI, KISS, DRY

- **Build what today's requirement needs.** A speculative feature costs everything afterwards that
  must keep it working. A generalisation built for one case is a guess about the second, and a
  wrong abstraction outlives the duplication it prevented, because callers have grown into it. An
  option nobody sets and a parameter always left at its default are branches never known to work.
- **The simplest construction that fully solves the problem**, which is not the shortest one.
  Prefer the boring mechanism: a function over a class, a dict over a registry. Simplicity is
  measured at the point of *use*.
- **DRY is about knowledge, not text.** Two fragments that look identical but answer to different
  actors are not duplication — merging them couples two things that must be free to move apart,
  and the next change arrives as a parameter, then a flag, then a branch. Two fragments that must
  change together are duplication even when they look nothing alike: a limit enforced in a
  validator and repeated in a schema. **Wait for the third occurrence.** The cure is often a shared
  constant or a shared type, not a new unit that has to be named.

## Definition of Done

The formatter, the linters, the strict type checker and the tests run first, in that order, each
clean with no new suppression. Then the eight checks no tool makes, skipped first under pressure:

- [ ] Every new identifier passes `naming.md`'s Self-Check and survives the relocation test
- [ ] Every new module and class answers to one actor — name who would ask to change it
- [ ] Every helper has a reason to exist: reuse, a required callable, hidden complexity, a test
      seam, or a named predicate — and every class has one of the six triggers in `classes.md`
- [ ] Constants sit at the top of the module, and **every top-level name not used outside is
      prefixed** — `find_unprefixed_names.py` reports nothing new
- [ ] No generically named unit contains concrete logic; no concrete rule lives in two places
- [ ] No `Any`, no magic literal, no `dict[str, Any]` crossing a layer; `@override` on every
      override, `Final` on every constant
- [ ] Every conversion preserves the cause; nothing returns `None`/`False`/`-1` to signal an error;
      errors are logged once, at the boundary, with no secrets or PII
- [ ] Every comment and docstring passes the relocation test; no credentials, URLs or
      environment-specific values are hardcoded
