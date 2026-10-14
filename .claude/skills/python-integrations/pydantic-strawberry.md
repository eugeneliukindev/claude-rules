# pydantic and strawberry

The seam between `python-pydantic` and `python-strawberry`, linked from both skills.

In strawberry 0.334 it is `strawberry.experimental.pydantic` — `type`, `input`, `interface`,
`error_type` — with no stable module beside it. The mypy plugin, `strawberry.ext.mypy_plugin`,
hooks only these decorators; without it `to_pydantic` and `from_pydantic` are `attr-defined`
errors.

### It is for an input whose pydantic model already exists; output is built from the domain

**Why:** an input shared with a REST route or a queue runs that model's validators through
`to_pydantic()`, so the constraints live once. A response model reused as a GraphQL type makes two
contracts change together, and the decorator writes `_strawberry_type` onto the pydantic class, so
one model backs one GraphQL type.

**Example:**
```python
# WRONG — the REST response model is also the GraphQL type: one change moves both contracts
@strawberry.experimental.pydantic.type(model=DogEntryResponse, name="DogEntry")
class DogEntryObject:
    id: strawberry.auto
    weight_kg: strawberry.auto


# CORRECT — the entry model the REST route already validates with, reused as the input
@strawberry.experimental.pydantic.input(model=DogEntryPayload, name="EnterDogInput")
class EnterDogInput:
    registration_number: strawberry.auto
    weight_kg: Decimal
```

### Validation runs in `to_pydantic()`, so a resolver reads the converted model, never the input

**Why:** GraphQL only type-checks the arguments; a resolver reading `entry.weight_kg` straight off
the input skips every constraint (*measured*: a negative weight passed, and `to_pydantic()` refused
it with `greater_than`). That `ValidationError` is the client's error: it is answered as a union
member or left unmasked; masked, it reaches the client as "Unexpected error." and the log as a
failure.

**Example:**
```python
# WRONG — a negative weight goes straight to the service; the model's validators never run
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def enter_dog(self, info: ShowInfo, entry: EnterDogInput) -> DogEntryObject:
        unchecked = DogEntry(
            registration_number=RegistrationNumber(entry.registration_number),
            weight_kg=entry.weight_kg,
        )
        accepted = await info.context.show_entries.enter(info.context.exhibitor, unchecked)
        return DogEntryObject.from_domain(accepted)


# CORRECT — the model's validators run first, and the service gets what they passed
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def enter_dog(self, info: ShowInfo, entry: EnterDogInput) -> DogEntryObject:
        validated = entry.to_pydantic()
        checked = DogEntry(
            registration_number=RegistrationNumber(validated.registration_number),
            weight_kg=validated.weight_kg,
        )
        accepted = await info.context.show_entries.enter(info.context.exhibitor, checked)
        return DogEntryObject.from_domain(accepted)
```

### A field annotated with a PEP 695 alias gets its GraphQL type written out

**Why:** `strawberry.auto` cannot resolve a named constrained type such as `type DogWeightKg =
Annotated[Decimal, Field(gt=0)]`, and decorating the input fails with `TypeError: … Unexpected type
'DogWeightKg'` (*measured*).

**Example:**
```python
# WRONG — weight_kg is a `type` alias on the model: the decorator cannot resolve it
@strawberry.experimental.pydantic.input(model=DogEntryPayload, name="EnterDogInput")
class EnterDogInput:
    registration_number: strawberry.auto
    weight_kg: strawberry.auto


# CORRECT — the GraphQL type stated on that field; the model still validates it
@strawberry.experimental.pydantic.input(model=DogEntryPayload, name="EnterDogInput")
class EnterDogInput:
    registration_number: strawberry.auto
    weight_kg: Decimal
```

### The GraphQL type lists each field it publishes; never `all_fields=True`

**Why:** the model is shared, and with `all_fields` a field added to it for another consumer becomes
part of the GraphQL schema too.
