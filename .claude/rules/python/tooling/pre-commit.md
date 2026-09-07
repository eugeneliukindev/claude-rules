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

## Configuration

Local hooks running through the environment manager, so the version comes from the lockfile and
the three copies — laptop, hook, CI — cannot disagree:

```yaml
# This list is the Definition of Done. A gate missing here wastes a CI run on something
# the author could have seen in a second; a hook missing there is only a suggestion.
repos:
  - repo: local
    hooks:
      - id: format
        name: format
        entry: uv run ruff format
        language: system
        types: [ python ]

      - id: lint
        name: lint
        entry: uv run ruff check --force-exclude
        language: system
        types: [ python ]

      - id: style
        name: style
        entry: uv run flake8
        language: system
        types: [ python ]

      - id: types
        name: types
        # Passing filenames would type-check them in isolation, and a strict run needs
        # the whole package to resolve imports.
        entry: uv run mypy
        language: system
        types: [ python ]
        pass_filenames: false

      - id: layers
        name: layers
        entry: uv run lint-imports
        language: system
        types: [ python ]
        pass_filenames: false

      - id: lockfile
        name: lockfile
        entry: uv lock --check
        language: system
        files: ^(pyproject\.toml|uv\.lock)$
        pass_filenames: false
```

In CI the same set runs over everything, so a bypassed hook cannot hide and a rule added today
still reaches the files written yesterday:

```
pre-commit run --all-files --show-diff-on-failure
```
