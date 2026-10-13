# Testing GraphQL

### Resolvers are tested through `schema.execute`, with a context of in-memory fakes

**Why:** the query, the variables and the context are the test's, and the result's `data` and
`errors` are asserted — the conversion, the union, the exception handler and the masking all run. A
resolver method called directly skips every one of them. `execute_sync` runs only a schema whose
resolvers are all `def`; on an `async` one it fails with "GraphQL execution failed to complete
synchronously."

**Example:**
```python
# WRONG — the method called directly: the handler that turns the error into ClaimNotFound never runs
async def test_approve_claim_answers_foreign_claim_as_not_found(mocker: MockerFixture) -> None:
    claim = make_claim(policyholder_id=_OTHER_POLICYHOLDER_ID)
    context = make_graphql_context(claims=[claim], scopes=frozenset({_APPROVE_SCOPE}))
    info = mocker.Mock(context=context)

    with pytest.raises(ClaimNotFoundError):
        await Mutation().approve_claim(info, claim.claim_id)


# CORRECT — through the schema: the answer the client would get
async def test_approve_claim_answers_foreign_claim_as_not_found() -> None:
    claim = make_claim(policyholder_id=_OTHER_POLICYHOLDER_ID)
    context = make_graphql_context(claims=[claim], scopes=frozenset({_APPROVE_SCOPE}))

    result = await _SCHEMA.execute(
        _APPROVE_CLAIM, variable_values={"claimId": str(claim.claim_id)}, context_value=context
    )

    assert result.errors is None
    assert result.data == {"approveClaim": {"__typename": "ClaimNotFound"}}
```

### Each limit is tested: one past it is answered with a visible error

**Why:** a limit nobody tests is found missing in production, and one answered with a masked
"Unexpected error." tells the client nothing — a query one level too deep, an alias too many, a
`first` over the ceiling.
