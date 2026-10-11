# A New Project's Configuration

## Contents

- The starting `pyproject.toml`
- ruff selects `ALL` and argues each ignore
- mypy's extra error codes, and one type checker
- pytest's strict mode and warnings as errors
- ruff's runtime-evaluated tables for pydantic and FastAPI

This is how to lay the configuration out, not a contract: the versions, the rule selection and the
ignores are a start the owner adapts. What carries over is the shape — the floor stated once, strict
mypy with extra codes, `select = ["ALL"]` with every ignore argued on its line. Coverage settings
are `python-pytest`'s; the import-linter contracts join when the package has a second layer
(`python-layers`). `.gitignore` adds every cache these tools create to what `uv init` writes.

## The Starting `pyproject.toml`

Kept below the build backend `uv init` wrote, the file is complete.

```toml
[project]
name = "pantry"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "niquests>=3.21",
  "pydantic>=2.11",
]

[project.scripts]
pantry = "pantry.cli:main"

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
plugins = ["pydantic.mypy"]   # with pydantic: BaseSettings() type-checks without every field
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
  "CPY001",   # preview rule; ignored so enabling preview does not demand a header
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
source = ["pantry"]

[tool.coverage.report]
show_missing = true
exclude_also = [
  "if TYPE_CHECKING:",
  "@overload",
  "assert_never\\(",
  "raise NotImplementedError",
]
```

### ruff selects `ALL`, and each ignore names its code and its reason

**Why:** a rule turned off is visible and argued once; a rule never turned on is invisible, and the
families a hand-picked list leaves out are the ones nobody thought of. The ignores above are the
ones ruff itself reports as conflicting, plus a project decision. A lint rule that disagrees with
these rules — `EM102` or `TRY003` against the f-string messages `errors.md` asks for, `TD002`
against an ownerless `TODO` — is the owner's call, made the same way.

**Example:**
```toml
# WRONG — a hand-picked list: the bugbear, security and annotation families are never checked
[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

# CORRECT — everything, minus what is argued on its line
[tool.ruff.lint]
select = ["ALL"]
ignore = [
  "COM812",   # conflicts with the formatter
]
```

### mypy enables the error codes `strict` leaves off, and is the only type checker

**Why:** `strict` does not turn on `explicit-override`, `exhaustive-match` or `ignore-without-code`,
and those three enforce rules `python-types` otherwise only asks for. mypy and pyright side by side
each want different suppressions, and a codebase checked by both ends up switching off the check
that reports a suppression nobody needs.

**Example:**
```toml
# WRONG — strict alone: an override without @override and an open match both pass
[tool.mypy]
python_version = "3.12"
strict = true

# CORRECT — the codes strict does not enable
[tool.mypy]
python_version = "3.12"
strict = true
enable_error_code = ["explicit-override", "exhaustive-match", "ignore-without-code"]
```

### pytest runs strict, with warnings as errors

**Why:** `strict = true` in `[tool.pytest]` (pytest 9) turns on strict markers, strict config,
strict `xfail` and strict parametrization ids together — a misspelt marker is an error, not a test
silently selected by nothing. `filterwarnings = ["error"]` fails the run the day a deprecation
warning appears, not the day the API is removed.

**Example:**
```toml
# WRONG — a typo in a marker selects nothing, and deprecations scroll past
[tool.pytest]
testpaths = ["tests"]

# CORRECT — unknown markers and every warning fail the run
[tool.pytest]
strict = true
testpaths = ["tests"]
filterwarnings = ["error"]
```

### ruff's runtime-evaluated tables name every pydantic base and FastAPI route decorator in use

**Why:** ruff's `TC` rules move an import used only in annotations under `TYPE_CHECKING`; pydantic
and FastAPI read those annotations at runtime, so the suggested fix breaks the model or the route
on import. The rules move an import only when annotations are not evaluated at definition — a
`from __future__ import annotations` module, or a 3.14 floor — so on 3.12 or 3.13 without either
the table waits for that day. Every model base the project defines joins the base classes.

**Example:**
```toml
# WRONG — the fix moves `from pantry.recipes import Recipe` out of a route's runtime reach
[tool.ruff.lint]
select = ["ALL"]

# CORRECT — the annotations pydantic and FastAPI evaluate keep their imports real
[tool.ruff.lint.flake8-type-checking]
runtime-evaluated-base-classes = ["pydantic.BaseModel", "pydantic_settings.BaseSettings"]
runtime-evaluated-decorators = ["fastapi.APIRouter.get", "fastapi.APIRouter.post"]
```
