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

- The context is a typed class, and resolvers read it through one `GraphQLInfo` alias
- The context is built from the services the root built, and adds only what is request-scoped
- A permission class is the coarse gate, attached through `PermissionExtension`
- Ownership is decided by the service, and someone else's claim is answered as not found

## DataLoaders

**Before writing a field that loads by key — a nested object, a list of related rows — read
[dataloaders.md](dataloaders.md)** — one loader per request, results in key order, bounded batches.

- Every field that loads by key goes through the request's `DataLoader`
- The `load_fn` returns one result per key, in key order
- A batch is one statement, and `max_batch_size` bounds it
- A loader is built per request, never by the root
- A loader over owned data calls a service method that takes the caller

## Building the Schema

**Before building the schema or the router, adding a list field, mapping a domain error or
configuring `MaskErrors`, read [schema.md](schema.md)** — query limits, a ceiling on every list,
discovery closed, errors as union members, masking and logging only the unexpected.

- Depth, tokens and aliases are limited together, each extension passed as a class or a factory
- Every list field takes `first`, with a ceiling the resolver enforces
- Where the schema is private, introspection, the IDE and field suggestions close together
- A classified domain error is a member of the field's result union, converted by a schema handler
- `MaskErrors` masks only what an unexpected exception raised, and `process_errors` logs only that

## Inputs and the Published Schema

**Before writing a mutation's input, changing a published field or setting up the schema's CI,
read [contract.md](contract.md)** — inputs converted by `to_domain()`, idempotency keys, the SDL
diffed in CI, breaking changes found by graphql-core, deprecation before removal.

- An input is a `@strawberry.input` type converted by `to_domain()`
- A mutation a client retries carries an idempotency key, minted by the client once per operation
- The SDL is exported, checked in, and compared in CI
- A breaking change is found by graphql-core, not by eye
- A field is deprecated before it is removed, and removed once its traffic has stopped

## Subscriptions

**Before writing a subscription or configuring the WebSocket route, read
[subscriptions.md](subscriptions.md)** — an async generator that releases what it holds, one
protocol, and per-connection limits.

- A subscription is an async generator that releases what it holds, through `aclosing`
- The router speaks one protocol, `graphql-transport-ws`
- The per-connection limits are set to what a client needs

## Testing

**Before testing resolvers or the limits, read [testing.md](testing.md)** — `schema.execute` with
fakes, and each limit answered visibly.

- Resolvers are tested through `schema.execute`, with a context of in-memory fakes
- Each limit is tested: one past it is answered with a visible error

## With Other Libraries

**Before mounting a strawberry GraphQL app in FastAPI, read
[fastapi-strawberry.md](../python-integrations/fastapi-strawberry.md)** — the context getter as an
authenticating dependency, on `HTTPConnection`.

- The GraphQL router's context getter is a dependency, and it is where authentication happens
- The context is a plain `BaseContext` subclass, never a frozen dataclass
- The getter takes `HTTPConnection`, not `Request`

**Before using `strawberry.experimental.pydantic`, read
[pydantic-strawberry.md](../python-integrations/pydantic-strawberry.md)** — for inputs whose
boundary model exists, validation in `to_pydantic()`, the mypy plugin, PEP 695 aliases, and no
`all_fields`.

- It is for an input whose pydantic model already exists; output is built from the domain
- Validation runs in `to_pydantic()`, so a resolver reads the converted model, never the input
- A field annotated with a PEP 695 alias gets its GraphQL type written out
- The GraphQL type lists each field it publishes; never `all_fields=True`
