---
name: python-pydantic
description: >-
  pydantic v2 practice: models at process boundaries only and never in the domain, the
  model_-prefixed methods that replace the deprecated v1 names, strict ConfigDict with extra
  forbidden, Annotated field constraints named once and reused, field and model validators that
  stay pure, serialization and exclude_unset as contract decisions, TypeAdapter built once,
  discriminated unions, and BaseSettings validated at startup. Use when Python code imports
  pydantic, defines a BaseModel or BaseSettings, or validates an external payload.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# pydantic

Assumes v2.11 or later; everything below is checked against the 2.13 source.

## Where pydantic Belongs

- **At process boundaries only**: request and response shapes, message payloads, settings, rows from
  untrusted sources. Its job is parsing and validating external data.
- **Not in the domain.** Domain entities are frozen dataclasses; domain code never imports pydantic.
  A model that has stopped validating anything and is only carrying fields around should have been a
  dataclass — it is paying validation cost on every construction for nothing.
- Validate once, strictly, at the edge, and map into a frozen domain object through an explicit
  `to_domain()` / `from_domain()` (why: `python-boundaries`); what follows is how pydantic spells it.
- strawberry's experimental pydantic integration — a boundary model reused as a GraphQL input — is
  `python-strawberry`.

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
  Two kinds of model take `extra="ignore"` instead: a stored or queued payload, read by code older
  or newer than its writer (`python-boundaries`), and the claims of a token, whose set the identity
  provider owns (`python-auth`).

```python
# WRONG — lax defaults: "3" becomes 3, and an unknown field is dropped in silence
@final
class OrderLine(BaseModel):
    sku: str
    quantity: int

# CORRECT — strict, closed and frozen, configured once on the base every boundary model shares
class BoundaryModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

@final
class OrderLine(BoundaryModel):
    sku: str
    quantity: int
```

- **Strict models parse JSON with `model_validate_json`.** In JSON mode strict still accepts the
  ISO-8601 and UUID strings JSON has no other way to carry; in Python mode it demands real
  `datetime` and `UUID` objects, so every valid payload fails:

```python
# WRONG — json.loads hands strict validation strings where it wants datetime and UUID objects
event = Event.model_validate(json.loads(body))
# CORRECT — JSON mode: strict, and the wire formats of datetime and UUID still parse
event = Event.model_validate_json(body)
```

- **A framework that validates the dict it decoded itself is in Python mode too**, and strict
  answers every valid ISO-8601 or UUID string with a validation error — measured on FastAPI 0.143,
  a request body model with `strict=True` turned a correct payload into a 422. Where the raw bytes
  are at hand, validate them — FastStream's message body (`python-faststream`). Where they are not
  — a FastAPI body, which also feeds the OpenAPI schema — relax exactly the fields whose wire form
  is a string, once, and keep the model strict:

```python
# WRONG — a FastAPI body on the strict base: every valid deliver_after is a 422
@final
class PlaceOrderRequest(BoundaryModel):
    deliver_after: datetime
    quantity: int

# CORRECT — the string wire forms are lax by name; quantity="3" is still refused
type WireDatetime = Annotated[datetime, Field(strict=False)]

@final
class PlaceOrderRequest(BoundaryModel):
    deliver_after: WireDatetime
    quantity: int
```

- **`validate_by_name=True`** when an alias generator is in play, so both wire and Python names
  work. It replaces `populate_by_name`, discouraged since 2.11 and slated for deprecation in v3.
- Configure once on a shared base model rather than repeating the dict on every schema.

## Fields and Constraints

- **`Annotated[int, Field(ge=1, le=200)]`, not `x: int = Field(ge=1)`.** The annotated form keeps
  the default separate from the constraint, survives being aliased into a named type — which
  `python-types` asks for: a constrained type is named once — and reads the same in every position.
- **A model that is really immutable is immutable all the way down** — `frozen=True` plus
  `tuple[str, ...]` and `frozenset` instead of `list` and `set`. A parsed payload almost always is;
  a model that is built up step by step is not, and drops `frozen` instead of pretending. `frozen`
  stops reassigning a field, not appending to the list inside it.

```python
# WRONG — frozen, and still line.tags.append("gift") changes it
@final
class OrderLine(BoundaryModel):
    sku: Sku
    tags: list[str] = []

# CORRECT — nothing reachable from the model can change
@final
class OrderLine(BoundaryModel):
    sku: Sku
    tags: tuple[str, ...] = ()
```

- **`default_factory` is for a computed default** — a timestamp, a generated id. A mutable default
  needs none: pydantic copies it for every instance, unlike a dataclass.
- **`SecretStr` / `SecretBytes` for credentials**, so a stray repr or log line cannot leak them.

```python
# WRONG — repr(settings), a traceback or a debug log prints the key in full
@final
class Settings(BaseSettings):
    payment_api_key: str

# CORRECT — renders as '**********'; get_secret_value() is the one place it is read
@final
class Settings(BaseSettings):
    payment_api_key: SecretStr
```

## Validators

- **`@field_validator` for one field, `@model_validator` for cross-field rules.** Reaching for a
  model validator to check a single field puts the rule where nobody looks for it.
- **`mode="before"` transforms raw input; `mode="after"` checks an already-typed value.** Prefer
  `after` — it runs on the parsed type, so the body does not re-implement coercion.
- **A validator raises `ValueError`, or a domain error that inherits it** — the closest stdlib
  type, as `errors.md` asks — and pydantic turns it into a validation error with the field's
  location attached. An exception that is no `ValueError` escapes past `except ValidationError`
  and loses that location.

```python
# WRONG — InvalidSkuError is no ValueError: it escapes past except ValidationError, location lost
class InvalidSkuError(ShopError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"SKU {sku!r} does not match {_SKU_PATTERN.pattern}")
        self.sku = sku

# CORRECT — a ValueError too, so pydantic reports it as a validation error at the field
class InvalidSkuError(ShopError, ValueError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"SKU {sku!r} does not match {_SKU_PATTERN.pattern}")
        self.sku = sku


def _check_sku_format(sku: str) -> str:
    if not _SKU_PATTERN.fullmatch(sku):
        raise InvalidSkuError(sku)
    return sku

type Sku = Annotated[str, AfterValidator(_check_sku_format)]
```

- **Validators are pure.** No I/O, no database lookup, no clock — a model that validates by calling
  out cannot be constructed in a test without the world.

## Serialization

- **`model_dump_json()` beats `json.dumps(model_dump())`** — it serializes straight from the core
  schema, without building the intermediate dict.

```python
# WRONG — model_dump() keeps datetime and Decimal as objects, and json.dumps refuses them
body = json.dumps(receipt.model_dump())

# CORRECT — serialized straight from the core schema, every field in its wire format
body = receipt.model_dump_json()
```

- **`model_dump(mode="json")`** when a dict of JSON-safe primitives is genuinely needed; plain
  `model_dump()` keeps `datetime`, `UUID` and `Decimal` as objects.
- **`exclude_none` / `exclude_unset` / `exclude_defaults` are contract decisions, not formatting.**
  `exclude_unset` is the correct one for a PATCH-style payload; the other two silently change what a
  consumer sees.

```python
# WRONG — exclude_none drops an explicit null, so a PATCH can never clear the nickname
body = changes.model_dump_json(exclude_none=True)

# CORRECT — exactly the fields that were set, an explicit null included
body = changes.model_dump_json(exclude_unset=True)
```

- **`model_dump()` is not a mapper**: `Order(**schema.model_dump())` is the splat
  `python-boundaries` forbids. Write `to_domain()` / `from_domain()`.

## Performance

- **`TypeAdapter` is built once and reused.** Construction compiles a validator and is the expensive
  part; building one per call in a loop is the single most common pydantic performance bug.

```python
# WRONG — compiles a validator on every call
def parse_orders(payload: bytes) -> list[OrderPayload]:
    return TypeAdapter(list[OrderPayload]).validate_json(payload)

# CORRECT — compiled once, when the module loads
_ORDERS_ADAPTER: Final = TypeAdapter(list[OrderPayload])

def parse_orders(payload: bytes) -> list[OrderPayload]:
    return _ORDERS_ADAPTER.validate_json(payload)
```

- **`model_construct()` skips validation** — use it only for data you have already validated, such
  as rows you just wrote yourself. It is a sharp tool: it will happily build an invalid model.
- **Discriminated unions** (`Field(discriminator="kind")`) turn an O(n) try-every-member walk into a
  single dispatch, and produce a readable error instead of a wall of per-variant failures.

```python
# WRONG — every member is tried in turn, and a bad payload reports a failure per member
@final
class PaymentMessage(BoundaryModel):
    payment: CardPayment | BankTransfer

# CORRECT — dispatched on kind, and the error names only the member it chose
@final
class PaymentMessage(BoundaryModel):
    payment: Annotated[CardPayment | BankTransfer, Field(discriminator="kind")]
```

## Settings

- **`BaseSettings` is a boundary model like any other** — constructed once in the composition root,
  passed down, never imported as a module-level singleton.
- **Validate at startup.** A missing variable must crash the process immediately, not on the first
  request that happens to touch it.
