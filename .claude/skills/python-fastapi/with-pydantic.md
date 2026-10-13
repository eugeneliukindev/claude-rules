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

### uvicorn's factory takes no arguments; it builds `Settings()` and calls `create_app`

**Why:** `uvicorn --factory` calls the function with no arguments, so `create_app(settings)` cannot
be the one it names. A default of `Settings()` in the signature is evaluated at import, reading the
environment before anything asked for it. A zero-argument function builds the settings when
uvicorn calls it, and tests call `create_app` with the settings they need.

**Example:**
```python
# WRONG — the default is built at import: importing the module reads the environment
def create_app(settings: Settings = Settings()) -> FastAPI:
    app = FastAPI(lifespan=_lifespan_for(settings))
    app.include_router(tasks_router)
    return app


# CORRECT — `uvicorn --factory tracker.api:app_from_environment`; tests call create_app
def app_from_environment() -> FastAPI:
    return create_app(Settings())
```
