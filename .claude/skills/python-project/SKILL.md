---
name: python-project
description: >-
  Starts and maintains a uv Python project: init, the src layout, requires-python, the lock,
  dependency bounds and groups, py.typed, a starting pyproject.toml with mypy, ruff and pytest.
  Use when creating a project or package, editing pyproject.toml, choosing a Python floor, or
  adding, upgrading or auditing a dependency or dev tool. Not for a package's public surface
  (python-packaging).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Starting and Maintaining a Project

An existing repository's tool configuration is its owner's choice, and it wins; these defaults are
for the directory where nobody has chosen yet. Tests and coverage are `python-pytest`, a package's
public surface and its extras `python-packaging`, the import-linter contracts `python-layers`, and
an audit of the image's operating-system packages `python-container`.

### An application starts from `uv init --package`, a library from `uv init --lib`: the src layout

**Why:** with the package beside the tests, `import unitconv` in a test imports the working tree,
so a module missing from the built package still passes every test; under `src/` the tests import
the installed package, what users get. `--lib` also writes `py.typed`, without which every
consumer's type checker treats the library as untyped. `tests/` sits beside `src/`, and a helper
the package must not ship lives there. The build backend `uv init` writes stays unless there is a
reason.

### `requires-python` is the floor, and `[tool.mypy] python_version` repeats it

**Why:** the floor decides the syntax once — PEP 695 generics from 3.12, `TypeIs` from 3.13, `uuid7`
from 3.14 — and ends the per-file arguments. mypy does not read `requires-python`: it checks against
the interpreter it runs on, so a call to a 3.13 function passes on 3.14 and breaks on the declared
3.12. ruff does read it. `.python-version`, which `uv init` writes, pins the interpreter the team
develops on and may be newer than the floor.

**Example:**
```toml
# WRONG — mypy runs on 3.14 and accepts what the declared 3.12 cannot import
[project]
requires-python = ">=3.12"

[tool.mypy]
strict = true

# CORRECT — mypy checks against the floor
[project]
requires-python = ">=3.12"

[tool.mypy]
python_version = "3.12"
strict = true
```

### A direct dependency has a lower bound and no upper bound

**Why:** the lower bound is the version whose API the code uses. An upper bound in a library makes
it uninstallable beside any package that needs the next major, long before anything has broken; a
cap below the next minor once silently disabled a feature that existed only from that minor on, for
as long as the cap stood. An application's exact versions come from the lock, not from caps.
`uv add` writes the bound, locks and syncs in one step.

**Example:**
```toml
# WRONG — the cap refuses rich 15 before anything breaks; the pin refuses every other release
dependencies = [
  "click==8.2.1",
  "rich>=14,<15",
]

# CORRECT — the oldest version whose API the code uses, and nothing above it
dependencies = [
  "click>=8.2",
  "rich>=14",
]
```

### `uv.lock` is committed, and CI installs with `uv sync --locked`

**Why:** the lock makes every developer's and every CI run's environment the same, for an
application and a library alike; a library's users never see it. Plain `uv sync` re-resolves when
`pyproject.toml` has moved past the lock, so CI would test versions nobody locked; `--locked` fails
instead.

### Tools are a dependency group, never an extra

**Why:** `[dependency-groups]` (PEP 735) is what `uv sync` installs and the published package does
not carry. An extra — `[project.optional-dependencies]` — is a feature a user opts into, and lives
in the one module that imports it.

## Upgrades and Audits

**Before upgrading the lock or writing a CI job for dependencies, read [upgrades.md](upgrades.md)**
— the lock moved in a commit of its own, the floors tested by a `lowest-direct` job, `pip-audit`
pointed at the lock.

- The lock moves on purpose, in a commit of its own
- A lower bound is tested by a CI job that installs every direct dependency at its floor
- `pip-audit` reads the lock's export, not the environment it runs in

## A New Project's Configuration

**Before writing a new project's `pyproject.toml` tool tables, read
[new-project.md](new-project.md)** — a complete starting file, and why ruff selects `ALL`, which
mypy codes `strict` leaves off, and pytest's strict mode.

- ruff selects `ALL`, and each ignore names its code and its reason
- mypy enables the error codes `strict` leaves off, and is the only type checker
- pytest runs strict, with warnings as errors
