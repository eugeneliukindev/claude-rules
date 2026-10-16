---
paths:
  - "**/*.py"
---

# Python - Functions

## Parameters

- **Put the subject first, then required inputs, then dependencies and options by keyword after `*`.** The call reads as being about its subject, a new dependency never shifts a position, and the root binds dependencies with `partial`; make a payload a library hands in, its name meaning nothing to the caller, positional-only (`/`), and keep the order a framework dictates.
- **Turn values that travel together into one frozen dataclass.** The same parameters on five functions are a concept without a name; check its invariant once, in `__post_init__`.
- **Split a boolean that selects between two behaviours into two functions, or a `Literal` or `Enum`.** A flag hides two bodies behind one name, keyword-only or not; a keyword-only boolean that tunes one behaviour, like `sorted(reverse=)`, is fine when the branches share a body.
- **Read only the function's parameters, and pass in a clock, randomness and every setting.** A value read inside, like a timeout, a TTL or the statuses worth retrying, is an input no test fixes without patching.
- **Default a setting to its module constant in the signature or the constructor, and never pass the settings object.** A test then passes only what it needs, where `settings: Settings` makes it build the whole tree; the root, a test, a fixture and a framework-parsed signature (a route) read the constant, and a value a protocol fixes, a query, a dispatch table, a security allowlist, an uncompared identifier and a monotonic duration stay in the body.
- **Name each value a later call needs on its own line.** A value built inside another call's arguments hides a step, and naming one sibling while inlining the other suggests a difference that is not there; a trivial conversion or a literal stays inline.
- **Separate the steps (fetch, act, return) with one blank line, and put none inside a step.**

## Results

- **Give a query no side effect, and make a command return `None` or the outcome of its own effect.** A query can be called twice or skipped; a command returns what its effect produced, like `list.pop()` the item it removed, never a value a reader would take for a lookup and never behind a `get_` (`naming.md`).

## Extraction

- **Extract a helper only when it pays.** Extract for real reuse today, when a callback or a `key=` requires an object, to hide genuine complexity, when the parent would otherwise break its limits, for its own test seam, or for a named predicate (`control-flow.md`).
- **Inline a helper whose body is one call or one expression, that the reader opens anyway, or whose name is a moment rather than an action.** Its name and signature are an interface that pays only by hiding more than it exposes.
