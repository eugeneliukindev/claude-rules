---
name: python-strawberry
description: >-
  strawberry-graphql mechanics: wire types from domain objects, a typed context, DataLoaders,
  query limits, introspection off, errors as union results, permissions, subscriptions, tests, SDL
  checks. Use when code imports strawberry, defines a type, resolver, DataLoader, GraphQLRouter or
  schema extension, or serves or tests GraphQL. Not for verifying the caller's token (python-auth).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Strawberry GraphQL

Checked against strawberry-graphql 0.334 and graphql-core 3.3, by reading the installed source and
running every `CORRECT` below. Strawberry is 0.x and renames and deprecates between minor versions —
check the source of the version you pin. Mounting the GraphQL app in a web framework is that
framework's skill; how the caller's credential is verified is `python-auth`.

### The GraphQL package turns off `disallow_untyped_decorators` in one mypy override

**Why:** under `mypy --strict`, a decorator called with arguments —
`@strawberry.field(description=...)`, `@strawberry.mutation(extensions=[...])` — is reported as
`untyped-decorator`, because those overloads return `Any`; the bare `@strawberry.field` is typed.
Nothing calls a resolver by its attribute, so the package that holds them takes one named override
instead of an ignore on every resolver, and the rest of the code keeps the check.

**Example:**
```toml
# CORRECT — off only where strawberry's decorators are, never for the whole codebase
[tool.mypy]
strict = true

[[tool.mypy.overrides]]
module = ["claims.graphql.*"]
disallow_untyped_decorators = false  # strawberry types field(...) and mutation(...) as Any
```

### A union is a plain assignment, the one alias that is not a `type` statement

**Why:** strawberry reads the `Annotated` value at schema construction; a `type` statement hides it
behind a `TypeAliasType`, and construction fails with `Unexpected type`.

**Example:**
```python
# WRONG — schema construction fails with "Unexpected type"
type ApproveClaimResult = Annotated[
    ClaimObject | ClaimNotFound, strawberry.union("ApproveClaimResult")
]

# CORRECT — a plain assignment, which strawberry reads as it is
ApproveClaimResult = Annotated[ClaimObject | ClaimNotFound, strawberry.union("ApproveClaimResult")]
```

### A strawberry type is built from the domain object, never the domain object decorated

**Why:** the schema publishes every field of the class it is given, so a decorated domain class
publishes the next field anyone adds to it, and the domain imports the transport.
`strawberry.Private[...]` is a field the resolvers read and the schema never shows — here the key
the policyholder loader needs.

**Example:**
```python
# WRONG — the domain class is the wire type: the adjuster's notes are published, and any later field
@strawberry.type
@dataclass(frozen=True, slots=True, kw_only=True)
class Claim:
    claim_id: ClaimId
    policyholder_id: PolicyholderId
    amount: Decimal
    adjuster_notes: str


# CORRECT — the wire type names what it publishes and is built from the domain Claim
@strawberry.type(name="Claim")
class ClaimObject:
    id: UUID
    amount: Decimal
    policyholder_id: strawberry.Private[PolicyholderId]

    @classmethod
    def from_domain(cls, claim: Claim) -> Self:
        return cls(id=claim.claim_id, amount=claim.amount, policyholder_id=claim.policyholder_id)
```

### `name=` pins the published name of every type

**Why:** the schema takes type names from Python class names and field names from attributes,
camel-cased; without the pin, renaming a Python class renames a type every client queries. The
Python name carries the family suffix, the schema the domain word.

### A resolver converts its arguments, calls one service method, and converts the result

**Why:** a rule written in a resolver is reachable only through GraphQL; a worker or a second API
that performs the same operation skips it. The approval limit, the ownership check and the state
change are the service's; the resolver is `ClaimObject.from_domain(await service.method(...))`.

### A resolver that blocks is `async` and offloads: a `def` resolver runs on the event loop

**Why:** unlike a web framework's `def` handler, a `def` resolver is not sent to a thread pool;
strawberry calls it inside the event loop. Measured: three concurrent queries of a `def` resolver
sleeping 0.5 s took 1.5 s, all on the main thread. A `def` resolver that only computes from what it
already holds blocks nothing and stays a `def`.

**Example:**
```python
# CORRECT — the blocking call runs on a worker thread and the loop keeps serving
@strawberry.type
class Query:
    @strawberry.field
    async def payout(self, info: GraphQLInfo, payout_id: UUID) -> PayoutObject:
        payout = await asyncio.to_thread(info.context.payouts.fetch_payout, PayoutId(payout_id))
        return PayoutObject.from_domain(payout)
```

## The Context and Authorization

**Before writing the `context_getter`, the context class, a permission class or an ownership
check, read [context.md](context.md)** — a typed context behind one `GraphQLInfo` alias, the scope
gate through `PermissionExtension`, ownership decided by the service.

## DataLoaders

**Before writing a field that loads by key — a nested object, a list of related rows — read
[dataloaders.md](dataloaders.md)** — one loader per request, results in key order, bounded batches.

## Building the Schema

**Before building the schema or the router, adding a list field, mapping a domain error or
configuring `MaskErrors`, read [schema.md](schema.md)** — query limits, a ceiling on every list,
discovery closed, errors as union members, masking and logging only the unexpected.

## Inputs and the Published Schema

**Before writing a mutation's input, changing a published field or setting up the schema's CI,
read [contract.md](contract.md)** — inputs converted by `to_domain()`, idempotency keys, the SDL
diffed in CI, breaking changes found by graphql-core, deprecation before removal.

## Subscriptions

**Before writing a subscription or configuring the WebSocket route, read
[subscriptions.md](subscriptions.md)** — an async generator that releases what it holds, one
protocol, and per-connection limits.

## Testing

**Before testing resolvers or the limits, read [testing.md](testing.md)** — `schema.execute` with
fakes, and each limit answered visibly.

## With Other Libraries

**Before mounting a strawberry GraphQL app in FastAPI, read
[fastapi-strawberry.md](../python-integrations/fastapi-strawberry.md)** — the context getter as an
authenticating dependency, on `HTTPConnection`.

**Before using `strawberry.experimental.pydantic`, read
[pydantic-strawberry.md](../python-integrations/pydantic-strawberry.md)** — for inputs whose
boundary model exists, validation in `to_pydantic()`, the mypy plugin, PEP 695 aliases, and no
`all_fields`.
