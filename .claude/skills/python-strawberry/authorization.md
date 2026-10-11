# Authorization

### A permission class is the coarse gate, attached through `PermissionExtension`

**Why:** a scope or a role is checked before the resolver runs, with a fixed message whatever
failed (`python-auth`). The source documents the older `permission_classes=` wrapping as
deprecated. `PermissionExtension` publishes each class as a directive in the SDL —
`directive @hasScope on FIELD_DEFINITION` — so the schema names its authorization rules;
`use_directives=False` keeps them out. `has_permission` keeps the library's `Any` parameters, and an
annotated local states the context type once.

**Example:**
```python
# WRONG — the deprecated wrapping
@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[HasApproveScope])
    async def approve_claim(self, info: GraphQLInfo, claim_id: UUID) -> ApproveClaimResult:
        claim = await info.context.claims.approve_claim(info.context.principal, ClaimId(claim_id))
        return ClaimObject.from_domain(claim)


# CORRECT — the permission as an extension, checked before the resolver runs
@final
class HasScope(BasePermission):
    message = "Not allowed"

    def __init__(self, scope: str) -> None:
        self._scope = scope

    @override
    def has_permission(self, source: Any, info: strawberry.Info, **kwargs: Any) -> bool:
        context: GraphQLContext = info.context
        return self._scope in context.principal.scopes


@strawberry.type
class Mutation:
    @strawberry.mutation(extensions=[PermissionExtension(permissions=[HasScope(_APPROVE_SCOPE)])])
    async def approve_claim(self, info: GraphQLInfo, claim_id: UUID) -> ApproveClaimResult:
        claim = await info.context.claims.approve_claim(info.context.principal, ClaimId(claim_id))
        return ClaimObject.from_domain(claim)
```

### Ownership is decided by the service, and someone else's object is answered as not found

**Why:** the permission class has not seen the claim; the service loads it, so it decides. A
resolver that loads first and refuses second tells a stranger which ids exist — the IDOR rule of
`python-auth`. The service raises `ClaimNotFoundError` for a claim that is missing and for one that
is someone else's alike, and the schema answers both as the union member `ClaimNotFound`.

**Example:**
```python
# WRONG — "forbidden" for a foreign claim, "not found" for a missing one: the ids are enumerable
@strawberry.type
class Query:
    @strawberry.field
    async def claim(self, info: GraphQLInfo, claim_id: UUID) -> ClaimResult:
        claim = await info.context.claims.find_claim(ClaimId(claim_id))
        if claim is None:
            raise ClaimNotFoundError(ClaimId(claim_id))
        if claim.policyholder_id != info.context.principal.subject:
            raise GraphQLError("forbidden")
        return ClaimObject.from_domain(claim)


# CORRECT — the service checks ownership and raises the same error for both
@strawberry.type
class Query:
    @strawberry.field
    async def claim(self, info: GraphQLInfo, claim_id: UUID) -> ClaimResult:
        claim = await info.context.claims.get_claim(info.context.principal, ClaimId(claim_id))
        return ClaimObject.from_domain(claim)
```
