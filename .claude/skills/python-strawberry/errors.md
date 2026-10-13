# Errors

## Contents

- Classified errors are union members, converted by schema exception handlers
- `MaskErrors` masks only the unexpected
- The unexpected are logged once

GraphQL answers 200 with an `errors` list; the HTTP status says only that the request was
understood. A classified domain error becomes a stated answer and anything else a fixed message,
through two mechanisms.

### A classified domain error is a member of the field's result union, converted by a schema handler

**Why:** `exception_handlers=` on the schema converts an exception into an error type on every field
whose return union contains that type, so the mapping is in one place and the service raises its own
errors; a `try` in each resolver is a mapping repeated and, in the next resolver, forgotten.
Subscriptions are excluded.

**Example:**
```python
# WRONG — each resolver catches and converts, and the next one added lets the error escape
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def approve_claim(self, info: GraphQLInfo, claim_id: UUID) -> ApproveClaimResult:
        try:
            claim = await info.context.claims.approve_claim(
                info.context.principal, ClaimId(claim_id)
            )
        except ClaimNotFoundError as error:
            return ClaimNotFound(claim_id=error.claim_id, message=str(error))
        return ClaimObject.from_domain(claim)


# CORRECT — one handler on the schema answers the error on every field whose union has ClaimNotFound
@final
class _ClaimNotFoundHandler(strawberry.ExceptionHandler[ClaimNotFoundError, ClaimNotFound]):
    @override
    def handle(
        self, exception: ClaimNotFoundError, *, field: StrawberryField, info: strawberry.Info
    ) -> ClaimNotFound:
        return ClaimNotFound(claim_id=exception.claim_id, message=str(exception))


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def approve_claim(self, info: GraphQLInfo, claim_id: UUID) -> ApproveClaimResult:
        claim = await info.context.claims.approve_claim(info.context.principal, ClaimId(claim_id))
        return ClaimObject.from_domain(claim)


schema = strawberry.Schema(
    query=Query, mutation=Mutation, exception_handlers=[_ClaimNotFoundHandler()]
)
```

### `MaskErrors` masks only what an unexpected exception raised

**Why:** `MaskErrors()` with its default masks every error: measured, a syntax error, an unknown
field and a depth violation all became "Unexpected error.", and a client cannot fix a query it is
not told is wrong. Validation errors, permission refusals and a `GraphQLError` a resolver raised on
purpose stay as they are.

**Example:**
```python
# WRONG — the default predicate masks everything, the client's own mistakes included
extensions: list[Callable[[], SchemaExtension]] = [MaskErrors]


# CORRECT — only an error caused by an exception nobody classified is masked
def _is_unexpected(error: GraphQLError) -> bool:
    return error.original_error is not None and not isinstance(error.original_error, GraphQLError)


extensions: list[Callable[[], SchemaExtension]] = [
    partial(MaskErrors, should_mask_error=_is_unexpected)
]
```

### The unexpected errors are logged once, by an overridden `process_errors`

**Why:** `Schema.process_errors` logs every error at `ERROR` with its traceback on the
`strawberry.execution` logger, so a client's typo pages someone. Overridden, it logs only the
unexpected; it runs before `MaskErrors`, so it still sees the original exception.

**Example:**
```python
# WRONG — the default schema: a client's misspelt field is logged at ERROR with a traceback
schema = strawberry.Schema(query=Query, mutation=Mutation, extensions=extensions)


# CORRECT — only an exception nobody classified is logged, with its traceback and path
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


schema = _ServerErrorLoggingSchema(query=Query, mutation=Mutation, extensions=extensions)
```
