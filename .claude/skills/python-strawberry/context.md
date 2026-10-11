# The Context

## Contents

- A `BaseContext` subclass behind one `GraphQLInfo` alias
- Built from what the lifespan built
- Authentication once, in the getter
- `HTTPConnection`, so the WebSocket route works too

`context_getter` is a FastAPI dependency — it can `Depends` on others — and runs once per request.

### The context is a `BaseContext` subclass, and resolvers read it through one `GraphQLInfo` alias

**Why:** the router accepts a `BaseContext` subclass or a dict, and raises `InvalidCustomContext`
for anything else; a dict is `dict[str, Any]` in every resolver, so a misspelt key or a wrong type
is found at runtime. With a class and `type GraphQLInfo = strawberry.Info[GraphQLContext, None]`,
every `info.context` is typed.

**Example:**
```python
# WRONG — a dict: every resolver reads Any, and a misspelt key fails only when it runs
async def get_context(
    connection: HTTPConnection, principal: Annotated[Principal, Depends(require_principal)]
) -> dict[str, object]:
    return {"principal": principal, "claims": connection.state.claim_service}


# CORRECT — a class, and one alias every resolver takes
@final
class GraphQLContext(BaseContext):
    def __init__(
        self,
        *,
        principal: Principal,
        claims: ClaimService,
        policyholder_loader: DataLoader[PolicyholderId, Policyholder | None],
    ) -> None:
        super().__init__()
        self.principal = principal
        self.claims = claims
        self.policyholder_loader = policyholder_loader


type GraphQLInfo = strawberry.Info[GraphQLContext, None]
```

### The getter reads the services the lifespan built, and builds only what is request-scoped

**Why:** the getter runs on every request; a pool or a client built in it is built per request, and
a module-level service is the global `python-wiring` forbids. The lifespan puts the services on the
connection's state; the getter adds the principal and the loaders, which belong to one request.

**Example:**
```python
# WRONG — an engine and its pool built for every request, never closed
async def get_context(
    connection: HTTPConnection, principal: Annotated[Principal, Depends(require_principal)]
) -> GraphQLContext:
    engine = create_async_engine(connection.app.state.database_url)
    policyholders = PostgresPolicyholderRepository(engine)
    return GraphQLContext(
        principal=principal,
        claims=ClaimService(PostgresClaimRepository(engine)),
        policyholder_loader=DataLoader(load_fn=partial(_load_policyholders, policyholders)),
    )


# CORRECT — the lifespan's services, and a loader for this request
async def get_context(
    connection: HTTPConnection, principal: Annotated[Principal, Depends(require_principal)]
) -> GraphQLContext:
    claims: ClaimService = connection.state.claim_service
    policyholders: PolicyholderRepository = connection.state.policyholder_repository
    return GraphQLContext(
        principal=principal,
        claims=claims,
        policyholder_loader=DataLoader(load_fn=partial(_load_policyholders, policyholders)),
    )
```

### Authentication happens in the getter, once, before any GraphQL runs

**Why:** a GraphQL API is one route, so this is the protected router of `python-fastapi`: the
principal is a dependency of the getter, and its failure is an HTTP 401 before any resolver runs. A
resolver that reads the token itself is one more place to forget it. How the token is verified is
`python-auth`.

**Example:**
```python
# WRONG — each resolver authenticates on its own, and the next one added may not
@strawberry.type
class Query:
    @strawberry.field
    async def claim(self, info: GraphQLInfo, claim_id: UUID) -> ClaimObject:
        principal = info.context.verifier.verify(info.context.request.headers["authorization"])
        claim = await info.context.claims.get_claim(principal, ClaimId(claim_id))
        return ClaimObject.from_domain(claim)


# CORRECT — the getter depends on the principal; resolvers only read it
@strawberry.type
class Query:
    @strawberry.field
    async def claim(self, info: GraphQLInfo, claim_id: UUID) -> ClaimObject:
        claim = await info.context.claims.get_claim(info.context.principal, ClaimId(claim_id))
        return ClaimObject.from_domain(claim)
```

### The getter takes `HTTPConnection`, not `Request`

**Why:** the same getter serves the WebSocket route, which has no `Request`; measured with
`request: Request`, every subscription failed with a `TypeError` while every HTTP test passed. A
dependency raising `HTTPException` refuses the WebSocket handshake with the same 401.

**Example:**
```python
# WRONG — HTTP works; the WebSocket route cannot supply a Request, and every subscription fails
async def get_context(
    request: Request, principal: Annotated[Principal, Depends(require_principal)]
) -> GraphQLContext:
    claims: ClaimService = request.state.claim_service
    policyholders: PolicyholderRepository = request.state.policyholder_repository
    return GraphQLContext(
        principal=principal,
        claims=claims,
        policyholder_loader=DataLoader(load_fn=partial(_load_policyholders, policyholders)),
    )


# CORRECT — HTTPConnection is what both the HTTP and the WebSocket routes have
async def get_context(
    connection: HTTPConnection, principal: Annotated[Principal, Depends(require_principal)]
) -> GraphQLContext:
    claims: ClaimService = connection.state.claim_service
    policyholders: PolicyholderRepository = connection.state.policyholder_repository
    return GraphQLContext(
        principal=principal,
        claims=claims,
        policyholder_loader=DataLoader(load_fn=partial(_load_policyholders, policyholders)),
    )
```
