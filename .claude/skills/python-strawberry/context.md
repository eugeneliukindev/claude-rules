# The Context and Authorization

A web integration calls the context getter once per request; how its framework hands the getter
the request, and how it refuses an unauthenticated one, is that framework's skill. The caller
arrives already verified, as the application's own `ClaimsCaller` — the policyholder it acts for
and the scopes it was granted — so no resolver reads a token.

### The context is a typed class, and resolvers read it through one `GraphQLInfo` alias

**Why:** a dict is `dict[str, Any]` in every resolver, so a misspelt key or a wrong type is found at
runtime. With a class and `type GraphQLInfo = strawberry.Info[GraphQLContext, None]`, every
`info.context` is typed.

**Example:**
```python
# WRONG — a dict: every resolver reads Any, and a misspelt key fails only when it runs
def build_context(caller: ClaimsCaller, *, services: ClaimServices) -> dict[str, object]:
    return {"caller": caller, "claims": services.claims}


# CORRECT — a class, and one alias every resolver takes
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimsCaller:
    policyholder_id: PolicyholderId
    scopes: frozenset[str]


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class GraphQLContext:
    caller: ClaimsCaller
    claims: ClaimService
    policyholder_loader: DataLoader[PolicyholderId, Policyholder | None]


type GraphQLInfo = strawberry.Info[GraphQLContext, None]
```

### The context is built from the services the root built, and adds only what is request-scoped

**Why:** the getter runs on every request; a pool or a client built in it is built per request and
never closed. The composition root builds the services once; the getter adds the caller and a
`DataLoader(load_fn=partial(_load_policyholders, policyholders=services.policyholders))` for each
loader, which belong to one request.

### A permission class is the coarse gate, attached through `PermissionExtension`

**Why:** a scope is checked before the resolver runs, with a fixed message whatever failed. The
source documents the older `permission_classes=` wrapping as deprecated. `PermissionExtension`
publishes each class as a directive in the SDL — `directive @hasScope on FIELD_DEFINITION` — so the
schema names its authorization rules; `use_directives=False` keeps them out. `has_permission` keeps
the library's `Any` parameters, and an annotated local states the context type once.

**Example:**
```python
# CORRECT — the permission as an extension, checked before the resolver runs
@final
class HasScope(BasePermission):
    message = "Not allowed"

    def __init__(self, scope: str) -> None:
        self._scope = scope

    @override
    def has_permission(self, source: Any, info: strawberry.Info, **kwargs: Any) -> bool:
        context: GraphQLContext = info.context
        return self._scope in context.caller.scopes


@strawberry.type
class Mutation:
    @strawberry.mutation(extensions=[PermissionExtension(permissions=[HasScope(_APPROVE_SCOPE)])])
    async def approve_claim(self, info: GraphQLInfo, claim_id: UUID) -> ApproveClaimResult:
        claim = await info.context.claims.approve_claim(info.context.caller, ClaimId(claim_id))
        return ClaimObject.from_domain(claim)
```

### Ownership is decided by the service, and someone else's claim is answered as not found

**Why:** the permission class has not seen the claim; the service loads it, so it decides. A
resolver that loads first and refuses second tells a stranger which ids exist. The service takes
the caller and raises `ClaimNotFoundError` for a claim that is missing and for one that is someone
else's alike, and the schema's exception handler answers both as the union member `ClaimNotFound`.
