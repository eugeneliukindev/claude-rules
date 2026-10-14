# Building the Schema

## Contents

- Depth, tokens and aliases limited together, by extension classes
- A ceiling on every list field
- Introspection, the IDE and field suggestions closed together
- Classified errors are union members, converted by schema exception handlers
- `MaskErrors` masks only the unexpected, and the unexpected are logged once

A client writes the query, so the server bounds it before running it. Enabled batching
(`batching_config={"max_operations": n}`) multiplies every limit by `n`. No operation allowlist
ships: it is a `SchemaExtension` of your own or the gateway's job. `allow_queries_via_get=False`
where nothing caches GET responses.

### Depth, tokens and aliases are limited together, each extension passed as a class or a factory

**Why:** `QueryDepthLimiter` counts through fragments — measured — but not breadth: depth five with
a hundred items per level is ten billion objects. The token limit bounds the query's size, and the
alias limit stops one field being asked for a thousand times under different names. An instance in
`extensions=[...]` raises a `DeprecationWarning`, which `filterwarnings = ["error"]` turns into a
failing suite, and is shared by every operation; a list built apart from the call is annotated —
unannotated, a class beside a `partial` is `list[object]`.

**Example:**
```python
# CORRECT — depth, size and aliases bounded before any resolver runs
def build_claims_schema(*, limits: QueryLimits = QueryLimits()) -> strawberry.Schema:
    extensions: list[Callable[[], SchemaExtension]] = [
        partial(QueryDepthLimiter, max_depth=limits.max_depth),
        partial(MaxTokensLimiter, max_token_count=limits.max_tokens),
        partial(MaxAliasesLimiter, max_alias_count=limits.max_aliases),
    ]
    return strawberry.Schema(query=Query, mutation=Mutation, extensions=extensions)
```

### Every list field takes `first`, with a ceiling the resolver enforces

**Why:** a list with no argument returns whatever the table holds, and the depth limit cannot see
it. The ceiling raises `GraphQLError`, which the client sees; a keyset cursor gives the next page.

**Example:**
```python
# CORRECT — a page, bounded, with the cursor of the last claim to continue from
@strawberry.type
class Query:
    @strawberry.field
    async def claims(
        self, info: GraphQLInfo, first: int = _DEFAULT_CLAIMS_PER_PAGE, after: str | None = None
    ) -> ClaimPage:
        if not 0 < first <= _MAX_CLAIMS_PER_PAGE:
            raise GraphQLError(f"first must be between 1 and {_MAX_CLAIMS_PER_PAGE}")
        page = await info.context.claims.list_claims(
            info.context.caller, limit=first, after=decode_claim_cursor(after)
        )
        return ClaimPage.from_domain(page)
```

### Where the schema is private, introspection, the IDE and field suggestions close together

**Why:** each is a way to read the schema. GraphiQL is on by default, and without
`disable_field_suggestions=True` a typo is answered with `Did you mean 'approveClaim'?`, so the
field names come out one guess at a time even with introspection off: `DisableIntrospection` in the
extensions, `config=StrawberryConfig(disable_field_suggestions=True)` on the schema, and
`graphql_ide=None` on the router, together.

### A classified domain error is a member of the field's result union, converted by a schema handler

**Why:** GraphQL answers 200 with an `errors` list, so a classified error needs a stated answer.
`exception_handlers=` on the schema converts an exception into an error type on every field
whose return union contains that type, so the mapping is in one place and the service raises its own
errors; a `try` in each resolver is a mapping repeated and, in the next resolver, forgotten.
Subscriptions are excluded.

**Example:**
```python
# CORRECT — one handler on the schema answers the error on every field whose union has ClaimNotFound
@final
class _ClaimNotFoundHandler(strawberry.ExceptionHandler[ClaimNotFoundError, ClaimNotFound]):
    @override
    def handle(
        self, exception: ClaimNotFoundError, *, field: StrawberryField, info: strawberry.Info
    ) -> ClaimNotFound:
        return ClaimNotFound(claim_id=exception.claim_id, message=str(exception))


schema = strawberry.Schema(
    query=Query, mutation=Mutation, exception_handlers=[_ClaimNotFoundHandler()]
)
```

### `MaskErrors` masks only what an unexpected exception raised, and `process_errors` logs only that

**Why:** `MaskErrors()` with its default masks every error: measured, a syntax error, an unknown
field and a depth violation all became "Unexpected error.", and a client cannot fix a query it is
not told is wrong. `Schema.process_errors` logs every error at `ERROR` with its traceback on the
`strawberry.execution` logger, so a client's typo pages someone. Overridden, it logs only the
unexpected; it runs before `MaskErrors`, so it still sees the original exception.

**Example:**
```python
# WRONG — everything masked, the client's own mistakes included, and every typo logged at ERROR
schema = strawberry.Schema(query=Query, mutation=Mutation, extensions=[MaskErrors])


# CORRECT — only an exception nobody classified is masked, and logged with its path
def _is_unexpected(error: GraphQLError) -> bool:
    return error.original_error is not None and not isinstance(error.original_error, GraphQLError)


@final
class _ServerErrorLoggingSchema(strawberry.Schema):
    @override
    def process_errors(
        self, errors: list[GraphQLError], execution_context: ExecutionContext | None = None
    ) -> None:
        for error in errors:
            if _is_unexpected(error):
                logger.error(
                    "graphql resolver failed",
                    exc_info=error.original_error,
                    extra={"graphql_path": error.path},
                )


schema = _ServerErrorLoggingSchema(
    query=Query,
    mutation=Mutation,
    extensions=[partial(MaskErrors, should_mask_error=_is_unexpected)],
)
```
