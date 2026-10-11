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

### The wiring is tested through the app, with the lifespan running, asserting `data` and `errors`

**Why:** the context getter, the authentication dependency and the router only run through the
app: `with TestClient(app)`, on `httpx2`, or the async client and `LifespanManager`
(`python-fastapi`). A GraphQL failure is still a 200, so a test that asserts only the status passes
on an error.

**Example:**
```python
# WRONG — 200 is also what a failed query returns
def test_claim_query_through_the_app(app: FastAPI, claim: Claim) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/graphql",
            json={"query": _CLAIM_QUERY, "variables": {"claimId": str(claim.claim_id)}},
            headers=_AUTHORIZATION,
        )

    assert response.status_code == HTTPStatus.OK


# CORRECT — the status, no errors, and the data the client reads
def test_claim_query_through_the_app(app: FastAPI, claim: Claim) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/graphql",
            json={"query": _CLAIM_QUERY, "variables": {"claimId": str(claim.claim_id)}},
            headers=_AUTHORIZATION,
        )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert "errors" not in body
    assert body["data"] == {"claim": {"id": str(claim.claim_id)}}
```

### Each limit is tested: one past it is answered with a visible error

**Why:** a limit nobody tests is found missing in production, and one answered with a masked
"Unexpected error." tells the client nothing — a query one level too deep, an alias too many, a
`first` over the ceiling.

**Example:**
```python
# WRONG — only that it failed: a masked error passes too
async def test_query_past_the_depth_limit_is_refused() -> None:
    result = await _SCHEMA.execute(_TOO_DEEP_QUERY, context_value=make_graphql_context())

    assert result.errors


# CORRECT — refused, and told why
async def test_query_past_the_depth_limit_is_refused() -> None:
    result = await _SCHEMA.execute(_TOO_DEEP_QUERY, context_value=make_graphql_context())

    assert result.errors is not None
    assert "exceeds maximum operation depth" in result.errors[0].message
```
