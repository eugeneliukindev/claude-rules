# FastAPI and pydantic

The seam between `python-fastapi` and `python-pydantic`, linked from both skills. A body the
framework decodes relaxes its string-carried fields in `python-pydantic`.

### The validation error handler drops `input` from what it returns

**Why:** FastAPI's default 422 answer repeats every rejected value — measured on FastAPI 0.143, a
password refused for being too short came back in the response body, where proxies, browser tools
and client logs keep it. The handler keeps the location, the message and the type, and nothing the
client sent.

**Example:**
```python
# WRONG — the default handler: {"loc": ["body", "password"], ..., "input": "hunter2"}
def build_choir_api(*, database_url: str) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with RosterStore.connect(database_url) as roster:
            yield {"choir": ChoirService(roster=roster)}

    app = FastAPI(lifespan=lifespan)
    app.include_router(singers_router)
    return app


# CORRECT — where and why the body was refused, never what it contained
async def _validation_error_response(request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, RequestValidationError):
        raise error
    details = [
        {"loc": failure["loc"], "msg": failure["msg"], "type": failure["type"]}
        for failure in error.errors()
    ]
    return JSONResponse({"detail": details}, status_code=HTTPStatus.UNPROCESSABLE_ENTITY)


def build_choir_api(*, database_url: str) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with RosterStore.connect(database_url) as roster:
            yield {"choir": ChoirService(roster=roster)}

    app = FastAPI(lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, _validation_error_response)
    app.include_router(singers_router)
    return app
```

### A route's response is a model it builds from the domain object, named by the return annotation

**Why:** returned as is, a domain object is validated into the response model by attribute, so a
field added to the domain later is one rename away from being published; built field by field by
`from_domain`, the response says what leaves. The return annotation is the response model — a
separate `response_model=` restates it and drifts.

**Example:**
```python
# WRONG — the domain object goes out, and response_model restates the annotation's job
@singers_router.get("/singers/{singer_id}", response_model=SingerResponse)
async def show_singer(singer_id: SingerId, choir: ChoirDep) -> Singer:
    return await choir.get_singer(singer_id)


# CORRECT — the response is built from the domain object, and the annotation names it
@singers_router.get("/singers/{singer_id}")
async def show_singer(singer_id: SingerId, choir: ChoirDep) -> SingerResponse:
    return SingerResponse.from_domain(await choir.get_singer(singer_id))
```
