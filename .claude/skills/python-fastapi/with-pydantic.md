# FastAPI With pydantic

A model's strictness, its fields and its validators are `python-pydantic`; a body the framework
decodes relaxes its string-carried fields there.

### The validation error handler drops `input` from what it returns

**Why:** FastAPI's default 422 answer repeats every rejected value — measured on FastAPI 0.143, a
password refused for being too short came back in the response body, where proxies, browser tools
and client logs keep it. The handler keeps the location, the message and the type, and nothing the
client sent.

**Example:**
```python
# WRONG — the default handler: {"loc": ["body", "password"], ..., "input": "hunter2"}
app = FastAPI(lifespan=lifespan)
app.include_router(accounts_router)


# CORRECT — where and why the body was refused, never what it contained
async def _validation_error_response(request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, RequestValidationError):
        raise error
    details = [
        {"loc": failure["loc"], "msg": failure["msg"], "type": failure["type"]}
        for failure in error.errors()
    ]
    return JSONResponse({"detail": details}, status_code=HTTPStatus.UNPROCESSABLE_ENTITY)


app = FastAPI(lifespan=lifespan)
app.add_exception_handler(RequestValidationError, _validation_error_response)
app.include_router(accounts_router)
```

### A route's response is a model it builds from the domain object, named by the return annotation

**Why:** returned as is, a domain object is serialized through the response model by attribute, so
a field added to the domain later is one rename away from being published; built field by field by
`from_domain`, the response says what leaves (`python-boundaries`). The return annotation is the
response model — a separate `response_model=` restates it and drifts.

**Example:**
```python
# WRONG — the domain object goes out, and response_model restates the annotation's job
@accounts_router.get("/accounts/{account_id}", response_model=AccountResponse)
async def read_account(account_id: AccountId, accounts: AccountServiceDep) -> Account:
    return await accounts.get(account_id)


# CORRECT — the response is built from the domain object, and the annotation names it
@accounts_router.get("/accounts/{account_id}")
async def read_account(account_id: AccountId, accounts: AccountServiceDep) -> AccountResponse:
    return AccountResponse.from_domain(await accounts.get(account_id))
```
