---
name: python-pydantic
description: >-
  pydantic v2 mechanics: model_ methods, strict config, Annotated constraints, pure validators,
  serialization, TypeAdapter, discriminated unions, BaseSettings. Use when code imports pydantic,
  defines a BaseModel or BaseSettings, or validates a payload with it. Not for where a boundary
  model belongs or how it maps to the domain (python-boundaries).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# pydantic

Assumes v2.11 or later; checked against pydantic 2.14 and pydantic-settings 2.15. Where a
validating model belongs, and how it maps to the domain, is `python-boundaries`.

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

### Validating models share one strict, closed, frozen base

**Why:** lax defaults turn `"3"` into `3` and drop an unknown field in silence. `strict=True`,
`extra="forbid"`, `frozen=True`, and `allow_inf_nan=False`, because strict still lets a `float` take
`NaN` and `Infinity` from JSON. It is configured once, on a shared base. A model whose writer it does
not control — a stored or queued payload read by code older or newer than its writer, the claims
of a token whose set the issuer owns — takes `extra="ignore"` instead. An instant is
`AwareDatetime`, which refuses a value without an offset, and a queued payload pins its version with
`Literal[1]`. With an alias generator, `validate_by_name=True` — it replaces `populate_by_name`.

**Example:**
```python
# WRONG — lax defaults: "3" becomes 3, and an unknown field is dropped in silence
@final
class SeedSelection(BaseModel):
    variety_code: str
    packets: int


# CORRECT — strict, closed and frozen, configured once on the base every boundary model shares
class StrictPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)


@final
class SeedSelection(StrictPayload):
    variety_code: str
    packets: int
```

### A strict model parses raw JSON with `model_validate_json`

**Why:** in JSON mode strict still accepts the ISO-8601 and UUID strings JSON has no other way to
carry; in Python mode it demands real `datetime` and `UUID` objects, so a dict from `json.loads`
fails every valid payload.

**Example:**
```python
# WRONG — json.loads hands strict validation strings where it wants datetime and UUID objects
def parse_restock(body: bytes) -> SeedsRestocked:
    return SeedsRestocked.model_validate(json.loads(body))


# CORRECT — JSON mode: strict, and the wire formats of datetime and UUID still parse
def parse_restock(body: bytes) -> SeedsRestocked:
    return SeedsRestocked.model_validate_json(body)
```

### A body a framework decodes for you relaxes exactly its string-carried fields, by name

**Why:** a framework that validates the dict it decoded is in Python mode, and strict answers every
valid ISO-8601 or UUID string with an error — measured, a strict body model behind a web framework
turned a correct payload into a 422. Where the raw bytes are at hand they are validated as JSON;
where they are not — a body the framework decodes and documents itself — the string wire forms are
made lax once, by name, and everything else stays strict.

**Example:**
```python
# WRONG — a framework-decoded body on the strict base: every valid sow_after is a 422
@final
class ReserveSeedsRequest(StrictPayload):
    sow_after: datetime
    packets: int


# CORRECT — the string wire form is lax by name; packets="3" is still refused
type WireDatetime = Annotated[datetime, Field(strict=False)]


@final
class ReserveSeedsRequest(StrictPayload):
    sow_after: WireDatetime
    packets: int
```

## Fields

### A constraint is `Annotated[..., Field(...)]`, and a frozen model is immutable all the way down

**Why:** the annotated form keeps the default apart from the constraint and survives being aliased
into a named type. `frozen=True` stops reassigning a field, not appending to the
list inside it — a parsed payload takes `tuple` and `frozenset`. A model built step by step drops
`frozen` rather than pretending. A mutable default needs no `default_factory`: pydantic copies it
per instance; `default_factory` is for a computed default — a timestamp, a generated id.

**Example:**
```python
# WRONG — frozen, and still selection.tags.append("organic") changes it
@final
class SeedSelection(StrictPayload):
    variety_code: VarietyCode
    packets: int = Field(default=1, ge=1, le=5)
    tags: list[str] = []


# CORRECT — nothing reachable from the model can change, and the constraint is a named type
type PacketCount = Annotated[int, Field(ge=1, le=5)]


@final
class SeedSelection(StrictPayload):
    variety_code: VarietyCode
    packets: PacketCount = 1
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
# WRONG — InvalidVarietyCodeError is no ValueError: it escapes past except ValidationError, location lost
class InvalidVarietyCodeError(CatalogueError):
    def __init__(self, variety_code: str) -> None:
        super().__init__(f"Variety code {variety_code!r} is not two letters and four digits")
        self.variety_code = variety_code


# CORRECT — a ValueError too, so pydantic reports it as a validation error at the field
class InvalidVarietyCodeError(CatalogueError, ValueError):
    def __init__(self, variety_code: str) -> None:
        super().__init__(f"Variety code {variety_code!r} is not two letters and four digits")
        self.variety_code = variety_code


def _check_variety_code(variety_code: str) -> str:
    if not _VARIETY_CODE_PATTERN.fullmatch(variety_code):
        raise InvalidVarietyCodeError(variety_code)
    return variety_code


type VarietyCode = Annotated[str, AfterValidator(_check_variety_code)]
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

- JSON comes from `model_dump_json`, a dict of primitives from `model_dump(mode="json")`
- `exclude_none`, `exclude_unset` and `exclude_defaults` are contract decisions

## Unions

**Before validating a field that may be one of several models, read [unions.md](unions.md)** — a
discriminator instead of trying every member.

- A union of models is discriminated on a literal field

## Settings

**Before defining a `BaseSettings` or a credential field, read [settings.md](settings.md)** — built
validated at startup, `SecretStr` for credentials, `extra="ignore"` on
classes that share a `.env` file.

- `BaseSettings` is validated at startup, with credentials as `SecretStr`
- Settings classes that share one `.env` file each set `extra="ignore"`

## With Other Libraries

**Before declaring a FastAPI request or response model, or answering a validation error, read
[fastapi-pydantic.md](../python-integrations/fastapi-pydantic.md)** — `input` dropped from the 422,
the response built from the domain and named by the return annotation.

**Before typing a FastStream subscriber's message as a pydantic model, read
[faststream-pydantic.md](../python-integrations/faststream-pydantic.md)** — the raw body to the
handler, validated there in JSON mode.

**Before building a pydantic model from a SQLAlchemy row, read
[pydantic-sqlalchemy.md](../python-integrations/pydantic-sqlalchemy.md)** — no `from_attributes` on
an ORM row; the model is built from the domain object.

**Before using `strawberry.experimental.pydantic`, read
[pydantic-strawberry.md](../python-integrations/pydantic-strawberry.md)** — for inputs whose
boundary model exists, validation in `to_pydantic()`, the mypy plugin, PEP 695 aliases, and no
`all_fields`.
