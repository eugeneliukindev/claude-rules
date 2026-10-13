---
name: python-strawberry
description: >-
  strawberry-graphql mechanics: wire types from domain objects, a typed context, DataLoaders,
  query limits, introspection off, errors as union results, permissions, subscriptions, tests, SDL
  checks. Use when code imports strawberry, defines a type, resolver, DataLoader, GraphQLRouter or
  schema extension, or serves or tests GraphQL.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Strawberry GraphQL

Checked against strawberry-graphql 0.333, graphql-core 3.3, FastAPI 0.143, Starlette 1.7 and
pydantic 2.14, by reading the installed source and running every `CORRECT` below. Strawberry is
0.x and renames and deprecates between minor versions — check the source of the version you pin.
The factory, the lifespan and `Depends` are `python-fastapi`; construction and lifetime
`python-wiring`. This file is where strawberry's mechanisms meet those rules.

### The GraphQL package turns off `disallow_untyped_decorators` in one mypy override

**Why:** under `mypy --strict`, a decorator called with arguments —
`@strawberry.field(description=...)`, `@strawberry.mutation(extensions=[...])` — is reported as
`untyped-decorator`, because those overloads return `Any`; the bare `@strawberry.field` is typed.
Nothing calls a resolver by its attribute, so the package that holds them takes one named override
instead of an ignore on every resolver, and the rest of the code keeps the check.

**Example:**
```toml
# WRONG — the check is off for the whole codebase, to quiet one package
[tool.mypy]
strict = true
disallow_untyped_decorators = false

# CORRECT — off only where strawberry's decorators are
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

**Why:** a `@strawberry.type` is a response model (`python-boundaries`). The schema publishes every
field of the class it is given, so a decorated domain class publishes the next field anyone adds to
it, and the domain imports the transport (`python-layers`). `strawberry.Private[...]` is a field the
resolvers read and the schema never shows — here the key the policyholder loader needs.

**Example:**
```python
# WRONG — the domain class is the wire type: the adjuster's notes are published, and any later field
@strawberry.type
@dataclass(frozen=True)
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

### A resolver translates and calls one service method

**Why:** a resolver is an adapter, as a FastAPI route is (`python-fastapi`); a rule written in it is
reachable only through GraphQL, and a REST route or a worker that performs the same operation skips
it.

**Example:**
```python
# WRONG — the approval limit lives in the resolver; a worker approving the same claim skips it
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def approve_claim(self, info: GraphQLInfo, claim_id: UUID) -> ClaimObject:
        claim = await info.context.claims.get_claim(info.context.principal, ClaimId(claim_id))
        if claim.amount > _SINGLE_APPROVER_LIMIT:
            raise GraphQLError("a second approver is required")
        approved = await info.context.claims.mark_approved(claim.claim_id)
        return ClaimObject.from_domain(approved)


# CORRECT — the service owns the rule; the resolver converts and calls it
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def approve_claim(self, info: GraphQLInfo, claim_id: UUID) -> ClaimObject:
        claim = await info.context.claims.approve_claim(info.context.principal, ClaimId(claim_id))
        return ClaimObject.from_domain(claim)
```

### A resolver that blocks is `async` and offloads: a `def` resolver runs on the event loop

**Why:** unlike a FastAPI `def` route, a `def` resolver is not sent to a thread pool; strawberry
calls it inside the event loop. Measured: three concurrent queries of a `def` resolver sleeping 0.5
s took 1.5 s, all on the main thread. Anything that blocks is offloaded (`python-async`); a `def`
resolver that only computes from what it already holds blocks nothing and stays a `def`.

**Example:**
```python
# WRONG — the blocking client stops every other request on the worker while it waits
@strawberry.type
class Query:
    @strawberry.field
    def payout(self, info: GraphQLInfo, payout_id: UUID) -> PayoutObject:
        payout = info.context.payments.fetch_payout(PayoutId(payout_id))
        return PayoutObject.from_domain(payout)


# CORRECT — the blocking call runs on a worker thread and the loop keeps serving
@strawberry.type
class Query:
    @strawberry.field
    async def payout(self, info: GraphQLInfo, payout_id: UUID) -> PayoutObject:
        payout = await asyncio.to_thread(info.context.payments.fetch_payout, PayoutId(payout_id))
        return PayoutObject.from_domain(payout)
```

## The Context

**Before writing the `context_getter` or the context class, read [context.md](context.md)** — a
`BaseContext` subclass behind one `GraphQLInfo` alias, built from what the lifespan built,
authentication once in the getter, and `HTTPConnection` so subscriptions work.

## DataLoaders

**Before writing a field that loads by key — a nested object, a list of related rows — read
[dataloaders.md](dataloaders.md)** — one loader per request, results in key order, one statement
per batch, and the principal carried into a loader over owned data.

## The pydantic Integration

**Before using `strawberry.experimental.pydantic`, read [pydantic.md](pydantic.md)** — for inputs
whose boundary model exists, validation in `to_pydantic()`, the mypy plugin, PEP 695 aliases, and
no `all_fields`.

## Query Limits and Discovery

**Before building the schema or the router, or adding a list field, read [limits.md](limits.md)** —
extensions as classes, depth with token and alias limits, a ceiling on every list, and
introspection, the IDE and field suggestions closed together.

## Errors

**Before mapping a domain error or configuring `MaskErrors`, read [errors.md](errors.md)** —
classified errors as union members through schema exception handlers, masking only the unexpected,
and logging them once.

## Authorization

**Before adding a permission class or an ownership check, read
[authorization.md](authorization.md)** — the coarse gate through `PermissionExtension`, and
ownership decided by the service.

## Mutations

**Before writing a mutation's input, read [mutations.md](mutations.md)** — `@strawberry.input`
types converted by `to_domain()`, and an idempotency key on what a client retries.

## Subscriptions

**Before writing a subscription or configuring the WebSocket route, read
[subscriptions.md](subscriptions.md)** — an async generator that releases what it holds, one
protocol, and per-connection limits.

## Testing

**Before testing resolvers, the router or the limits, read [testing.md](testing.md)** —
`schema.execute` with fakes, the app with its lifespan, and each limit answered visibly.

## The Schema as a Contract

**Before changing a published field or setting up the schema's CI, read
[schema-contract.md](schema-contract.md)** — the SDL exported and diffed, breaking changes found by
graphql-core, and deprecation before removal.
