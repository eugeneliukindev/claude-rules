# Query Limits and Discovery

## Contents

- Extensions passed as classes or factories
- Depth, tokens and aliases limited together
- A ceiling on every list field
- Introspection, the IDE and field suggestions closed together

A client writes the query, so the server bounds it before running it. Batching is off by default;
enabled with `batching_config={"max_operations": n}`, every operation in the batch pays the limits
on its own, so `n` multiplies them. No persisted-query or operation-allowlist extension ships in
0.333: an allowlist is a `SchemaExtension` of your own or the gateway's job. GET runs queries and
refuses mutations (400) by default; `allow_queries_via_get=False` where nothing caches GET
responses.

### Extensions are passed as classes or factories, never instances

**Why:** in 0.333 an instance in `extensions=[...]` raises a `DeprecationWarning`, which
`filterwarnings = ["error"]` turns into a failing suite, and mypy already rejects; one instance
would also be shared by every operation. A list built apart from the call is annotated —
unannotated, a class beside a `partial` is `list[object]`.

**Example:**
```python
# WRONG — instances: deprecated, and one object is shared by every request
extensions: list[Callable[[], SchemaExtension]] = [
    QueryDepthLimiter(max_depth=_MAX_QUERY_DEPTH),
    DisableIntrospection(),
]

# CORRECT — a class or a factory: a fresh extension for every operation
extensions: list[Callable[[], SchemaExtension]] = [
    partial(QueryDepthLimiter, max_depth=_MAX_QUERY_DEPTH),
    DisableIntrospection,
]
```

### Depth, tokens and aliases are limited together

**Why:** `QueryDepthLimiter` counts through fragments — measured — but not breadth: depth five with
a hundred items per level is ten billion objects. The token limit bounds the query's size, and the
alias limit stops one field being asked for a thousand times under different names.

**Example:**
```python
# WRONG — depth alone: a shallow query with a thousand aliases passes
def build_schema(*, is_introspection_enabled: bool) -> strawberry.Schema:
    extensions: list[Callable[[], SchemaExtension]] = [
        partial(QueryDepthLimiter, max_depth=_MAX_QUERY_DEPTH),
    ]
    if not is_introspection_enabled:
        extensions.append(DisableIntrospection)
    return strawberry.Schema(query=Query, mutation=Mutation, extensions=extensions)


# CORRECT — depth, size and aliases bounded before any resolver runs
def build_schema(*, is_introspection_enabled: bool) -> strawberry.Schema:
    extensions: list[Callable[[], SchemaExtension]] = [
        partial(QueryDepthLimiter, max_depth=_MAX_QUERY_DEPTH),
        partial(MaxTokensLimiter, max_token_count=_MAX_QUERY_TOKENS),
        partial(MaxAliasesLimiter, max_alias_count=_MAX_ALIASES),
    ]
    if not is_introspection_enabled:
        extensions.append(DisableIntrospection)
    return strawberry.Schema(query=Query, mutation=Mutation, extensions=extensions)
```

### Every list field takes `first`, with a ceiling the resolver enforces

**Why:** a list with no argument returns whatever the table holds, and the depth limit cannot see
it. The ceiling raises `GraphQLError`, which the client sees, and a keyset cursor gives the next
page (`python-persistence`).

**Example:**
```python
# WRONG — every claim the policyholder has ever filed, in one response
@strawberry.type
class Query:
    @strawberry.field
    async def claims(self, info: GraphQLInfo) -> list[ClaimObject]:
        claims = await info.context.claims.list_claims(info.context.principal)
        return [ClaimObject.from_domain(claim) for claim in claims]


# CORRECT — a page, bounded, with the cursor of the last claim to continue from
@strawberry.type
class Query:
    @strawberry.field
    async def claims(
        self, info: GraphQLInfo, first: int = _DEFAULT_PAGE_SIZE, after: str | None = None
    ) -> ClaimPage:
        if not 0 < first <= _MAX_PAGE_SIZE:
            raise GraphQLError(f"first must be between 1 and {_MAX_PAGE_SIZE}")
        page = await info.context.claims.list_claims(
            info.context.principal, limit=first, after=decode_claim_cursor(after)
        )
        return ClaimPage.from_domain(page)
```

### Where the schema is private, introspection, the IDE and field suggestions close together

**Why:** each is a way to read the schema. GraphiQL is on by default, and without
`disable_field_suggestions=True` a typo is answered with `Did you mean 'approveClaim'?`, so the
field names come out one guess at a time even with introspection off.

**Example:**
```python
# WRONG — introspection off, while GraphiQL and the suggestions still publish the schema
schema = strawberry.Schema(query=Query, extensions=[DisableIntrospection])
graphql_router = GraphQLRouter(schema, context_getter=get_context)

# CORRECT — all three discovery paths closed together
schema = strawberry.Schema(
    query=Query,
    extensions=[DisableIntrospection],
    config=StrawberryConfig(disable_field_suggestions=True),
)
graphql_router = GraphQLRouter(schema, context_getter=get_context, graphql_ide=None)
```
