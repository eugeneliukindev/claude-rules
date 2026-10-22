---
name: python-review
description: Review the current Python change for design mistakes linters cannot see. Run with /python-review.
disable-model-invocation: true
context: fork
---

Review the current change: the uncommitted diff, or the branch against its base when the tree is clean.

1. Run the project's tests, linters and type checker first, and report what fails.
2. Read the diff and every caller of what it changes.
3. Report only defects: a broken caller, a broken rule from the Python rules in your context, a behaviour change nobody asked for. Each finding names the file and line, the rule it breaks, and the evidence, such as a command that fails or a caller it breaks.
4. Don't report style the linters own. Don't ask for defensive code, extra abstraction or tests for cases that cannot happen: a review that asks for more code is how changes grow.
5. End with `Verdict: ship` or `Verdict: fix N first`.
