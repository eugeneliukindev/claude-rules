---
name: python-pydantic
description: >-
  pydantic v2 mechanics for boundary models: model_ methods, strict config, Annotated constraints,
  pure validators, serialization choices, TypeAdapter, discriminated unions, BaseSettings. Use
  when code imports pydantic, defines a BaseModel or BaseSettings, or validates an external
  payload.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# pydantic

Assumes v2.11 or later; checked against 2.14. Where a validating model belongs — at the process
boundary only, mapped into a frozen domain object through `to_domain()` and `from_domain()` — is
`python-boundaries`; a model reused as a GraphQL input is `python-strawberry`; FastStream's message
body is `python-faststream`.

## The API and the Checker

### The v2 `model_` names, never the deprecated v1 ones, and mypy runs the pydantic plugin

**Why:** every v1 method is still present and marked deprecated — a silent migration debt — and the
prefix is what keeps a field named `dump` or `json` from shadowing the method; a public method on
your own model that could collide with a field is the same bug. Without `plugins =
["pydantic.mypy"]` every `Settings()` built from the environment is `Missing named argument` for
each required field. `model_config = ConfigDict(...)` replaces the inner `class Config`.

| Deprecated | Use |
|---|---|
| `.dict()` | `.model_dump()` |
| `.json()` | `.model_dump_json()` |
| `.parse_obj()` | `.model_validate()` |
| `.parse_raw()` | `.model_validate_json()` |
| `.construct()` | `.model_construct()` |
| `.schema()` | `.model_json_schema()` |
| `.copy()` | `.model_copy()` |

## Configuration

### ruff's `runtime-evaluated-base-classes` names every model base

**Why:** ruff's `TC` rules move an import used only in an annotation under `TYPE_CHECKING`; pydantic
reads a model's annotations at runtime, so the suggested fix breaks the model on import. They move
it only where annotations are not evaluated at definition — a `from __future__ import annotations`
module, or a 3.14 floor. Every base the project defines for its models joins the list.

**Example:**
```toml
# WRONG — the fix moves a field's type import out of the model's runtime reach
[tool.ruff.lint]
select = ["ALL"]

# CORRECT — the annotations pydantic evaluates keep their imports real
[tool.ruff.lint.flake8-type-checking]
runtime-evaluated-base-classes = ["pydantic.BaseModel", "pydantic_settings.BaseSettings"]
```

### Boundary models share one strict, closed, frozen base

**Why:** lax defaults turn `"3"` into `3` and drop an unknown field in silence. `strict=True`,
`extra="forbid"`, `frozen=True`, and `allow_inf_nan=False`, because strict still lets a `float` take
`NaN` and `Infinity` from JSON (`python-boundaries`). It is configured once, on a shared base. Two
kinds of model take `extra="ignore"` instead: a stored or queued payload, read by code older or
newer than its writer, and the claims of a token, whose set the identity provider owns
(`python-auth`). An instant is `AwareDatetime`, which refuses a value without an offset, and a
queued payload pins its version with `Literal[1]`. With an alias generator, `validate_by_name=True`
— it replaces `populate_by_name`.

**Example:**
```python
# WRONG — lax defaults: "3" becomes 3, and an unknown field is dropped in silence
@final
class LoanLine(BaseModel):
    isbn: str
    copies: int


# CORRECT — strict, closed and frozen, configured once on the base every boundary model shares
class BoundaryModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)


@final
class LoanLine(BoundaryModel):
    isbn: str
    copies: int
```

### A strict model parses raw JSON with `model_validate_json`

**Why:** in JSON mode strict still accepts the ISO-8601 and UUID strings JSON has no other way to
carry; in Python mode it demands real `datetime` and `UUID` objects, so a dict from `json.loads`
fails every valid payload.

**Example:**
```python
# WRONG — json.loads hands strict validation strings where it wants datetime and UUID objects
def parse_return(body: bytes) -> BookReturned:
    return BookReturned.model_validate(json.loads(body))


# CORRECT — JSON mode: strict, and the wire formats of datetime and UUID still parse
def parse_return(body: bytes) -> BookReturned:
    return BookReturned.model_validate_json(body)
```

### A body a framework decodes for you relaxes exactly its string-carried fields, by name

**Why:** a framework that validates the dict it decoded is in Python mode, and strict answers every
valid ISO-8601 or UUID string with an error — measured, a strict body model behind a web framework
turned a correct payload into a 422. Where the raw bytes are at hand they are validated as JSON;
where they are not — a body the framework decodes and documents itself — the string wire forms are
made lax once, by name, and everything else stays strict.

**Example:**
```python
# WRONG — a framework-decoded body on the strict base: every valid due_on is a 422
@final
class ReserveBookRequest(BoundaryModel):
    due_on: datetime
    copies: int


# CORRECT — the string wire form is lax by name; copies="3" is still refused
type WireDatetime = Annotated[datetime, Field(strict=False)]


@final
class ReserveBookRequest(BoundaryModel):
    due_on: WireDatetime
    copies: int
```

## Fields

### A constraint is `Annotated[..., Field(...)]`, and a frozen model is immutable all the way down

**Why:** the annotated form keeps the default apart from the constraint and survives being aliased
into a named type (`python-types`). `frozen=True` stops reassigning a field, not appending to the
list inside it — a parsed payload takes `tuple` and `frozenset`. A model built step by step drops
`frozen` rather than pretending. A mutable default needs no `default_factory`: pydantic copies it
per instance; `default_factory` is for a computed default — a timestamp, a generated id.

**Example:**
```python
# WRONG — frozen, and still line.tags.append("signed") changes it
@final
class LoanLine(BoundaryModel):
    isbn: Isbn
    copies: int = Field(default=1, ge=1, le=5)
    tags: list[str] = []


# CORRECT — nothing reachable from the model can change, and the constraint is a named type
type CopyCount = Annotated[int, Field(ge=1, le=5)]


@final
class LoanLine(BoundaryModel):
    isbn: Isbn
    copies: CopyCount = 1
    tags: tuple[str, ...] = ()
```

## Validators

### A validator raises `ValueError`, or a domain error that inherits it, and calls nothing outside

**Why:** pydantic turns a `ValueError` into a validation error with the field's location; anything
else escapes past `except ValidationError` and loses it — so a domain error a validator raises also
inherits the closest stdlib type (`errors.md`). `@field_validator` checks one field, a
`@model_validator` cross-field rules; `mode="after"` runs on the parsed type and is preferred. A
validator is pure — no I/O, no lookup, no clock — or the model cannot be built in a test.

**Example:**
```python
# WRONG — InvalidIsbnError is no ValueError: it escapes past except ValidationError, location lost
class InvalidIsbnError(LibraryError):
    def __init__(self, isbn: str) -> None:
        super().__init__(f"ISBN {isbn!r} has a wrong check digit")
        self.isbn = isbn


# CORRECT — a ValueError too, so pydantic reports it as a validation error at the field
class InvalidIsbnError(LibraryError, ValueError):
    def __init__(self, isbn: str) -> None:
        super().__init__(f"ISBN {isbn!r} has a wrong check digit")
        self.isbn = isbn


def _check_isbn(isbn: str) -> str:
    if not _has_valid_check_digit(isbn):
        raise InvalidIsbnError(isbn)
    return isbn


type Isbn = Annotated[str, AfterValidator(_check_isbn)]
```

## Performance

### A `TypeAdapter` is built once and reused

**Why:** construction compiles a validator and is the expensive part; one per call in a loop is the
most common pydantic performance bug. `model_construct()` skips validation — only for data already
validated, such as rows just written; it will build an invalid model without a word.

## Serialization

**Before serializing a model — to JSON, to a dict, or as a PATCH — read
[serialization.md](serialization.md)** — `model_dump_json`, `mode="json"`, `exclude_unset` as a
contract, no `model_dump()` splat.

## Unions

**Before validating a field that may be one of several models, read [unions.md](unions.md)** — a
discriminator instead of trying every member.

## Settings

**Before defining a `BaseSettings` or a credential field, read [settings.md](settings.md)** — built
once at the root and validated at startup, `SecretStr` for credentials.
