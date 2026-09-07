---
paths:
  - "**/.pre-commit-config.yaml"
  - "**/.pre-commit-hooks.yaml"
---

# pre-commit

Runs the Python toolchain automatically, so a finding reaches the author at the keystroke that
caused it rather than an hour later. It is a runner, not a second standard: the checks it runs are
the ones in the Definition of Done, with the same settings.

## One Version, Not Three

- **Hooks run the tools from the project environment**, not from a separately resolved copy. Three
  installations of a linter at three versions produce three opinions, and the one that blocks you
  wins by accident.
- **Nothing is configured twice.** A hook that passes its own flags is a second configuration that
  will drift from `pyproject.toml`; the hook invokes the tool and the tool reads its own settings.

## Whole-Project Checks Take No Filenames

A type checker or an import-contract checker handed a list of changed files checks them in
isolation, cannot resolve their imports, and reports nonsense. Those hooks run over the project and
ignore the file list.

## Keeping It Usable

- **Fast checks first.** A hook set slow enough to interrupt thinking is a hook set that gets
  bypassed, and a bypassed hook protects nothing.
- **A hook that fires constantly on correct code is a broken hook.** Fix it or remove it: a check
  people have learned to ignore is worse than no check, because it teaches them to ignore the next
  one too.

## Configuration

Local hooks calling the tools through the environment manager, so the version comes from the
lockfile:

```yaml
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
        # No filenames: a strict run needs the whole package to resolve imports.
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
