# The Context

A web integration calls the context getter once per request; how its framework hands the getter
the request, and how it refuses an unauthenticated one, is that framework's skill.

### The context is a typed class, and resolvers read it through one `GraphQLInfo` alias

**Why:** a dict is `dict[str, Any]` in every resolver, so a misspelt key or a wrong type is found at
runtime. With a class and `type GraphQLInfo = strawberry.Info[GraphQLContext, None]`, every
`info.context` is typed.

**Example:**
```python
# WRONG — a dict: every resolver reads Any, and a misspelt key fails only when it runs
def build_context(principal: Principal, *, services: ClaimServices) -> dict[str, object]:
    return {"principal": principal, "claims": services.claims}


# CORRECT — a class, and one alias every resolver takes
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class GraphQLContext:
    principal: Principal
    claims: ClaimService
    policyholder_loader: DataLoader[PolicyholderId, Policyholder | None]


type GraphQLInfo = strawberry.Info[GraphQLContext, None]
```

### The context is built from the services the root built, and adds only what is request-scoped

**Why:** the getter runs on every request; a pool or a client built in it is built per request, and
a module-level service is the global `python-wiring` forbids. The composition root builds the
services once; the getter adds the principal and the loaders, which belong to one request. The
principal arrives already verified, so no resolver reads a token (`python-auth`).

**Example:**
```python
# WRONG — a pool opened for every request, and never closed
def build_context(principal: Principal, *, database_url: str) -> GraphQLContext:
    pool = open_database_pool(database_url)
    policyholders = PostgresPolicyholderRepository(pool)
    return GraphQLContext(
        principal=principal,
        claims=ClaimService(PostgresClaimRepository(pool)),
        policyholder_loader=DataLoader(
            load_fn=partial(_load_policyholders, policyholders=policyholders)
        ),
    )


# CORRECT — the root's services, and a loader for this request
def build_context(principal: Principal, *, services: ClaimServices) -> GraphQLContext:
    return GraphQLContext(
        principal=principal,
        claims=services.claims,
        policyholder_loader=DataLoader(
            load_fn=partial(_load_policyholders, policyholders=services.policyholders)
        ),
    )
```
