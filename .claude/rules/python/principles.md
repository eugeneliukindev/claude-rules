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

- **Make a module or a class answer to one actor, whoever asks for its changes.** Code answering to two actors ships the fix one asks for to the other; ask *who*, not *which layer*, and keep "does one thing" for functions. Keep knowledge both actors share once, on the data, and split it into two named rules once they mean different things.
- **Add a new case as data or a new file, never as a new branch in code that works.** Map kind to implementation through a mapping the root builds, so adding a kind is one entry and deleting one is as easy.
- **Make a subclass accept at least what its parent accepts, and return nothing wider.** Code written against the parent must work with the subclass; the checker catches a signature mismatch, and nothing checks behaviour.
- **Add no precondition, drop no promise and raise no new exception in a subclass.** Raise only what the contract names, or a kind of it.
- **Put in a contract only what its consumer calls.** A consumer handed more depends on it: its fake must implement it, and a change to a method it never calls reaches it. Split in what the consumer is given, not in the storage, and only once a consumer needing a different set exists; a catalogue every caller uses whole stays one contract.
- **Pass collaborators through the constructor, never build them inside.** The class depends on the contract and the composition root picks the implementation; one built inside cannot be replaced in a test, and the signature hides what it needs.

## YAGNI, KISS, DRY

- **Build what today's requirement needs: take the first option that fully works.** Drop what nobody asked for, then reuse what the codebase has, then the standard library, then an installed dependency, then the least new code; never add a dependency for a few lines. A speculative option or a pluggable format with one implementation is a branch never known to work; a function beats a class, a dict a registry, and the shortest diff wins once you know all it must touch.
- **Treat DRY as knowledge, not text, and wait for the third occurrence.** Identical fragments answering to different actors are not duplication, and merged they grow a flag; fragments that must change together are, however different they look, so a limit in a validator and in a schema is one constant both read.
