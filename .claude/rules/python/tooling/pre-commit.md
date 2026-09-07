---
paths:
  - "**/.pre-commit-config.yaml"
  - "**/.pre-commit-hooks.yaml"
---

# pre-commit

The hook set is the Definition of Done, run early. It exists to move a failure from CI back to the
keystroke that caused it — not to be a second, softer standard.

## The Hooks and the Gates Are the Same List

- **A gate that is not a hook wastes a CI run** on something the author could have seen in a second.
- **A hook that is not a gate is a suggestion**, and it will be skipped the first time it is
  inconvenient.
- When the two lists disagree, one of them is lying about what the project requires. Fix the list,
  not the symptom.

## CI Runs Them Too, on Everything

- **CI runs the whole set over all files**, not just the changed ones. Otherwise a hook can be
  bypassed at commit time and nothing ever notices, and a rule added today never reaches the files
  written yesterday.
- **In CI the hooks fail; they do not fix.** A pipeline that reformats and pushes hides the fact
  that the author's environment is not set up, and it makes the commit history disagree with what
  was reviewed.

## Pinning

- **Hook versions are pinned and updated deliberately**, in their own commit. An unpinned formatter
  changes its output on some unrelated day, and the resulting diff lands on whoever committed next.
- **The pinned version matches what CI and the environment install.** Three copies of a linter at
  three versions produce three opinions, and the one that blocks the merge wins by accident.

## Keeping It Usable

- **Fast checks at commit time, everything at push or in CI.** A hook set that takes a minute gets
  bypassed, and a bypassed hook set protects nothing.
- **Skipping is an event, not a habit.** Bypassing the hooks is for a genuine emergency, and the
  next commit puts it right.
- **A hook that fires constantly on correct code is a broken hook.** Fix or remove it: a check
  people have learned to ignore is worse than no check, because it trains them to ignore the next
  one too.
