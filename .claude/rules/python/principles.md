---
paths:
  - "**/*.py"
---

# Python - Principles

Weigh five principles in this order; when two rules conflict, the earlier principle wins:

1. Correct: the code does what its name and signature promise for every input the types allow, and fails loudly otherwise.
2. Readable: a teammate new to the file understands it top-down without opening others.
3. Simple: the least machinery that solves today's problem.
4. Typed: illegal states are unrepresentable, and the checker catches the mistake, not the reviewer.
5. Fast enough, by measurement: algorithmic sanity always, anything more with a profile in hand.

## The Change

- **Read the task and the code it touches, then list every place the change must reach.** Callers, tests, fixtures, config and exports are the scope; a feature nobody asked for is not.
- **Finish the whole change: the callers, tests and fixtures it breaks.** Be lazy about the solution, never about the change.
- **Fix a bug at its root, once, in the shared code, after finding every caller of the function you touch.** A fix in one caller leaves the others broken.
- **Between options of equal size, take the one that is correct on the edge cases.** Empty, zero, the last item, rounding, time zones.
- **Leave one small test for new non-trivial logic.** A branch, a loop, a parser, money or security, or a whole new script; a trivial change needs none.
- **Never cut validation at a trust boundary, error handling that prevents data loss, or security, and keep both in code you move or merge.**

## The System as a Whole

- **Keep a failure where it happened.** One bad input or one unreachable dependency never stops the run: name what is protected (this row, this source, this request), catch at exactly that boundary, and record the reason.
- **State the direction of degradation where the code makes the choice.** Skip, retry later, serve stale or return partial.
- **Make cost grow slower than the work.** Give every external collection a limit, every fan-out a semaphore, every run a deadline and every cache an expiry; "it has always been small" is not a bound.

## SOLID

- **S - give a module or a class one actor: the person or role who asks for its changes.** Name who would ask to change each function; two names mean two modules. Signs: a module mixing pricing with reporting, a class whose methods different callers use apart. Keep knowledge both actors share once, on the data; "does one thing" is the rule for a function, not this one.
- **O - add a new kind as data or a new file, never as a new `if`/`elif`/`match` branch in code that works.** Sign: an `if kind == ...` chain that every new kind edits. Map the kind to its implementation in a mapping the root builds, so adding a kind is one entry.
- **L - in a subclass, accept every type the parent accepts and return the same type or a subtype.** Never narrow a parameter (`Wine` to `SparklingWine`), add a check that rejects input the parent took, drop a promise, or raise an exception the contract does not name; raise a subclass of the one it names. Sign: a caller that `isinstance`-checks which subclass it got.
- **I - give a consumer a contract with only the methods it calls.** Signs: a fake that must implement methods its test never calls, an implementation that raises `NotImplementedError`, a consumer using two of eight methods. Split by what each consumer is given, once such a consumer exists; a contract every caller uses whole stays one.
- **D - take collaborators in the constructor, keyword-only after `*`, typed as the contract, and never build them inside.** Signs: `__init__` calls a concrete class (`SqlRepository(...)`), a domain module imports a driver or an HTTP client. The composition root builds the implementation and passes it in, so a test passes a fake.

## YAGNI, KISS, DRY

- **Build what today's requirement needs: take the first option that fully works.** Drop what nobody asked for, then reuse what the codebase has, then the standard library, then an installed dependency, then the least new code; never add a dependency for a few lines. A speculative option or a pluggable format with one implementation is a branch never known to work; a function beats a class, a dict a registry, and the shortest diff wins once you know all it must touch.
- **Treat DRY as knowledge, not text, and wait for the third occurrence.** Identical fragments answering to different actors are not duplication, and merged they grow a flag; fragments that must change together are, however different they look, so a limit in a validator and in a schema is one constant both read.
