---
name: python-pydantic
description: >-
  pydantic v2 practice: models at process boundaries only and never in the domain, the
  model_-prefixed methods that replace the deprecated v1 names, strict ConfigDict with extra
  forbidden, Annotated field constraints named once and reused, field and model validators that
  stay pure, serialization and exclude_unset as contract decisions, TypeAdapter built once,
  discriminated unions, and BaseSettings validated at startup. Use when Python code imports
  pydantic, defines a BaseModel or BaseSettings, or validates an external payload.
---

# pydantic

Assumes v2.11 or later; everything below is checked against the 2.13 source.

## Where pydantic Belongs

- **At process boundaries only**: request and response shapes, message payloads, settings, rows from
  untrusted sources. Its job is parsing and validating external data.
- **Not in the domain.** Domain entities are frozen dataclasses; domain code never imports pydantic.
  A model that has stopped validating anything and is only carrying fields around should have been a
  dataclass — it is paying validation cost on every construction for nothing.
- Validating once at the edge, strictness, and the explicit mapping into domain objects are
  `python-boundaries` rules; what follows is how pydantic spells them.

## The v2 API — the v1 Names Are Deprecated

Every v1 method is still present and every one is marked deprecated. Using them is a silent
migration debt, so use the `model_`-prefixed names:

| Deprecated | Use |
|---|---|
| `.dict()` | `.model_dump()` |
| `.json()` | `.model_dump_json()` |
| `.parse_obj()` | `.model_validate()` |
| `.parse_raw()` | `.model_validate_json()` |
| `.construct()` | `.model_construct()` |
| `.schema()` | `.model_json_schema()` |
| `.copy()` | `.model_copy()` |

The prefix is not decoration: it is what keeps a field named `dump` or `json` from shadowing the
method. Follow the same discipline in your own models — a public method on a model that could
collide with a field name is a bug waiting for the field to be added.

## Configuration

- **`model_config = ConfigDict(...)`**, not the v1 inner `class Config`.
- **Strict boundary models**: `strict=True` stops `"1"` becoming `1`; `extra="forbid"` stops
  unknown fields being dropped in silence; `frozen=True` makes the parsed object safe to pass on.
- **Strict models parse JSON with `model_validate_json`.** In JSON mode strict still accepts the
  ISO-8601 and UUID strings JSON has no other way to carry; in Python mode it demands real
  `datetime` and `UUID` objects, so every valid payload fails:

```python
# WRONG — json.loads hands strict validation strings where it wants datetime and UUID objects
event = Event.model_validate(json.loads(body))
# CORRECT — JSON mode: strict, and the wire formats of datetime and UUID still parse
event = Event.model_validate_json(body)
```

- **`validate_by_name=True`** when an alias generator is in play, so both wire and Python names
  work. It replaces `populate_by_name`, discouraged since 2.11 and slated for deprecation in v3.
- Configure once on a shared base model rather than repeating the dict on every schema.

## Fields and Constraints

- **`Annotated[int, Field(ge=1, le=200)]`, not `x: int = Field(ge=1)`.** The annotated form keeps
  the default separate from the constraint, survives being aliased into a named type, and reads the
  same in every position.
- **Name the constrained type once and reuse it** — `type PageSize = Annotated[int, Field(ge=1,
  le=200)]`. Repeating the same bounds in five signatures is five places to get it wrong.
- **`default_factory` for anything mutable or computed**; a bare mutable default is shared.
- **`SecretStr` / `SecretBytes` for credentials**, so a stray repr or log line cannot leak them.

## Validators

- **`@field_validator` for one field, `@model_validator` for cross-field rules.** Reaching for a
  model validator to check a single field puts the rule where nobody looks for it.
- **`mode="before"` transforms raw input; `mode="after"` checks an already-typed value.** Prefer
  `after` — it runs on the parsed type, so the body does not re-implement coercion.
- **A validator raises `ValueError`**, and pydantic turns it into a validation error with the
  field's location attached. Raising your own domain exception inside a validator loses that
  location.
- **Validators are pure.** No I/O, no database lookup, no clock — a model that validates by calling
  out cannot be constructed in a test without the world.

## Serialization

- **`model_dump_json()` beats `json.dumps(model_dump())`** — it serializes straight from the core
  schema, without building the intermediate dict.
- **`model_dump(mode="json")`** when a dict of JSON-safe primitives is genuinely needed; plain
  `model_dump()` keeps `datetime`, `UUID` and `Decimal` as objects.
- **`exclude_none` / `exclude_unset` / `exclude_defaults` are contract decisions, not formatting.**
  `exclude_unset` is the correct one for a PATCH-style payload; the other two silently change what a
  consumer sees.
- **`model_dump()` is not a mapper**: `Order(**schema.model_dump())` is the splat
  `python-boundaries` forbids. Write `to_domain()` / `from_domain()`.

## Performance

- **`TypeAdapter` is built once and reused.** Construction compiles a validator and is the expensive
  part; building one per call in a loop is the single most common pydantic performance bug.
- **`model_construct()` skips validation** — use it only for data you have already validated, such
  as rows you just wrote yourself. It is a sharp tool: it will happily build an invalid model.
- **Discriminated unions** (`Field(discriminator="kind")`) turn an O(n) try-every-member walk into a
  single dispatch, and produce a readable error instead of a wall of per-variant failures.

## Settings

- **`BaseSettings` is a boundary model like any other** — constructed once in the composition root,
  passed down, never imported as a module-level singleton.
- **Validate at startup.** A missing variable must crash the process immediately, not on the first
  request that happens to touch it.
