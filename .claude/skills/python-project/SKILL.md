---
name: python-project
description: >-
  Starting a Python project or package from an empty directory: uv init --package or --lib, the
  src layout, requires-python as the floor every other choice follows, uv.lock committed, direct
  dependencies with lower bounds and no upper bounds, dependency-groups (PEP 735) for tools versus
  extras for users, py.typed, and a starting pyproject.toml with the strict mypy block, ruff,
  pytest and coverage. Use when creating a new Python project, package, library or service, writing
  or reviewing pyproject.toml, choosing a Python version floor, or adding a dev tool or dependency.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Starting a Project

`core.md` leaves tool configuration to the repository, and in an existing one that stands: its
owner has chosen, and the choice wins. This file is for the directory where nobody has chosen yet —
the defaults that make every rule in these files checkable from the first commit.

## Layout

- **`uv init --package name` for an application, `uv init --lib name` for a library.** Both give
  the src layout — `src/name/__init__.py` — and the library also gets `py.typed`. Commit what `uv
  init` writes for the build backend rather than choosing another without a reason.
- **The src layout is the point.** With the package beside the tests, `import name` in a test
  imports the working tree, so a module missing from the built package still passes every test. With
  `src/`, the tests import the installed package — what users will get.
- **`py.typed` ships with every library**, or every consumer's type checker treats it as untyped
  and the annotations protect nobody outside the repository.
- **`tests/` beside `src/`**, never inside the package; a test helper the package must not ship
  lives under `tests/`.

## The Python Floor

- **`requires-python` is the oldest version the code runs on, and every other choice follows from
  it**: PEP 695 generics from 3.12, `TypeIs` from 3.13, `uuid7` from 3.14 (`python-types`). Pick it
  once; per-file arguments about syntax stop.
- **mypy does not read `requires-python`.** It checks against the interpreter it runs on, so code
  calling a 3.13 function passes on 3.14 and breaks on the declared 3.12. Set `python_version` in
  `[tool.mypy]` to the floor. ruff does read `requires-python`, and needs no `target-version`.
- **`.python-version` pins the interpreter for development**; `uv init` writes it. It is the
  version the team runs, and may be newer than the floor.

## Dependencies

- **Every direct dependency is declared with a lower bound and no upper bound** — the version whose
  API the code uses: `pydantic>=2.11`. An upper bound in a library makes it uninstallable beside
  any package that needs the next major, long before anything has broken; an application gets its
  exact versions from the lock, not from caps. A cap below the next minor once silently disabled
  a feature that existed only from that minor on, for as long as the cap stood.

```toml
# WRONG — the cap refuses pydantic 3 before anything breaks; the pin refuses every other release
dependencies = [
  "niquests==3.21.0",
  "pydantic>=2.11,<3",
]

# CORRECT — the oldest version whose API the code uses, and nothing above it
dependencies = [
  "niquests>=3.21",
  "pydantic>=2.11",
]
```

- **`uv.lock` is committed**, for an application and a library alike: it makes every developer's
  and every CI run's environment the same. A library's users never see it.
- **Tools go in `[dependency-groups]`** (PEP 735), which `uv sync` installs and a published package
  does not carry. **Extras** — `[project.optional-dependencies]` — are features a user opts into,
  and each one lives in the one module that imports it (`python-packaging`). A linter is never an
  extra.

```toml
# WRONG — an extra: `pip install shop[dev]` is now a published feature that installs a linter
[project.optional-dependencies]
dev = ["mypy>=2.4", "pytest>=9.0"]

# CORRECT — a group: uv sync installs it, and the published package does not carry it
[dependency-groups]
dev = ["mypy>=2.4", "pytest>=9.0"]
```

- **`uv add` and `uv add --dev`**, not hand-edited lists: they resolve, lock and sync in one step.

## A Starting `pyproject.toml`

```toml
[project]
name = "shop"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "niquests>=3.21",
  "pydantic>=2.11",
]

[project.scripts]
shop = "shop.cli:main"

[dependency-groups]
dev = [
  "mypy>=2.4",
  "pytest>=9.0",
  "pytest-cov>=7.0",
  "pytest-randomly>=5.0",
  "ruff>=0.16",
]

[tool.mypy]
python_version = "3.12"   # the floor: mypy does not read requires-python
strict = true
warn_unreachable = true
strict_equality_for_none = true
enable_error_code = [
  "explicit-override",     # @override on every override — otherwise a rename orphans a method
  "exhaustive-match",      # every match over a union or Enum is closed
  "ignore-without-code",   # a bare `# type: ignore` stops being possible
  "deprecated",            # using a @deprecated name is an error, not a runtime warning
  "possibly-undefined",    # a name bound in only one branch
  "redundant-expr",        # a condition that cannot change the outcome
  "redundant-self",
  "truthy-bool",           # `if some_object:` where the object is always truthy
  "truthy-iterable",
  "unused-awaitable",      # a coroutine created and never awaited
  "unimported-reveal",     # a committed reveal_type()
]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["ALL"]
ignore = [
  "COM812",   # conflicts with the formatter
  "CPY001",   # no copyright header in this project
  "D203",     # incompatible with D211, which is kept
  "D213",     # incompatible with D212, which is kept
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = [
  "D",        # a test's name is its specification; a docstring would repeat it
  "INP001",   # tests are collected by pytest, not imported as a package
  "S101",     # assert is how pytest checks
]

[tool.ruff.lint.flake8-type-checking]
# pydantic and FastAPI read these annotations at runtime: their imports stay real
runtime-evaluated-base-classes = ["pydantic.BaseModel", "pydantic_settings.BaseSettings"]
runtime-evaluated-decorators = [
  "fastapi.APIRouter.get",
  "fastapi.APIRouter.post",
  "fastapi.APIRouter.put",
  "fastapi.APIRouter.patch",
  "fastapi.APIRouter.delete",
]

[tool.pytest]
strict = true
addopts = ["-ra", "--cov", "--cov-branch"]
testpaths = ["tests"]
filterwarnings = ["error"]

[tool.coverage.run]
source = ["shop"]

[tool.coverage.report]
show_missing = true
exclude_also = [
  "if TYPE_CHECKING:",
  "@overload",
  "assert_never\\(",
  "raise NotImplementedError",
]
```

Kept the build backend `uv init` wrote above it, the file is complete. What each piece is for:

- **`select = ["ALL"]`, then ignore by code with a reason.** A rule turned off is visible and
  argued once; a rule never turned on is invisible. The ignores above are the ones ruff itself
  reports as conflicting, plus a project decision; a new one carries its reason on its line.
- **`strict = true` in `[tool.pytest]`** (pytest 9) turns on strict markers, strict config, strict
  `xfail` and strict parametrization ids together. `filterwarnings = ["error"]` makes a
  deprecation warning fail the run the day it appears, not the day the API is removed.
- **The mypy codes are the ones `strict` does not enable**; three of them enforce rules
  `python-types` otherwise only asks for. **One type checker**, not mypy and pyright side by side:
  each wants different suppressions, and a codebase checked by both ends up switching off the
  check that reports a suppression nobody needs.
- **`runtime-evaluated-*` keeps ruff's `TC` rules from moving an import under `TYPE_CHECKING`**
  when pydantic or FastAPI reads the annotation at runtime; without it, the suggested fix breaks
  the model or the route on import. Add a decorator there for every router method the project
  uses, and a base class for every model base it defines.
- **Coverage measures branches** (`testing.md`); the floor (`--cov-fail-under`) is added when there
  is a suite to hold it, and only ratchets up. `exclude_also` drops the lines no test can or should
  reach — type-checking blocks, overloads, exhaustiveness guards — so the number measures code.
- **CI installs with `uv sync --locked`**, which fails when `uv.lock` no longer matches
  `pyproject.toml` instead of quietly re-resolving — the lock the developers tested is the one CI
  runs.
- **The import-linter contracts** join this file when the package has a second layer
  (`python-layers`).

## `.gitignore`

What `uv init` writes, plus every tool cache the configuration above creates: `.venv/`,
`__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, and
`.hypothesis/` once property tests exist. A cache committed once is a merge conflict forever.
A `.dockerignore` is the opposite shape — an allowlist — and is in `python-container`.
