# FastAPI and SQLAlchemy

The seam between `python-fastapi` and `python-sqlalchemy`, linked from both skills.

### The lifespan builds the engine and the session maker, and disposes the engine as it ends

**Why:** a module-level engine is opened at import and closed by nobody, so every worker's pool
outlives its shutdown and the database logs the connections as dropped; an engine built in a
dependency is a pool per request. The lifespan builds one and disposes it after the last request.

**Example:**
```python
# WRONG — the engine is opened at import and never disposed
_ENGINE: Final = create_async_engine(os.environ["DATABASE_URL"])


def build_allotment_api() -> FastAPI:
    app = FastAPI()
    app.state.garden_sessions = async_sessionmaker(_ENGINE, expire_on_commit=False)
    app.include_router(plots_router)
    return app


# CORRECT — built when the app starts, disposed when it stops, whatever happened in between
def build_allotment_api(
    *,
    database_url: str,
    pool_size: int = _POOL_SIZE,
    max_plots_per_gardener: int = _MAX_PLOTS_PER_GARDENER,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        engine = create_async_engine(database_url, pool_size=pool_size, pool_pre_ping=True)
        build_allotments: AllotmentServiceFactory = partial(
            AllotmentService, max_plots_per_gardener=max_plots_per_gardener
        )
        try:
            yield {
                "garden_sessions": async_sessionmaker(engine, expire_on_commit=False),
                "build_allotments": build_allotments,
            }
        finally:
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.include_router(plots_router)
    return app
```

### The lifespan binds fixed values into a service factory; a request adds its session

**Why:** a service holds two kinds of input: values fixed for the app's life, and a session, one per
request. A dependency that looks the values up to build the service on every request is the
configuration lookup a dependency must not make, and a service built once in the lifespan cannot
hold a session. `partial` splits them: the lifespan binds what is application-scoped once, and the
dependency passes only what is request-scoped. The factory is typed as a calling protocol: as
`partial[AllotmentService]` mypy accepts a call that omits the transaction — measured — while the
protocol checks both the binding in the lifespan and the call in the dependency.

**Example:**
```python
# WRONG — every request reads the limit from the state to build the service
async def get_allotments(request: Request, session: GardenSessionDep) -> AllotmentService:
    max_plots_per_gardener: int = request.state.max_plots_per_gardener
    return AllotmentService(
        plots=SqlPlotRepository(session=session),
        transaction=session,
        max_plots_per_gardener=max_plots_per_gardener,
    )


# CORRECT — the values were bound in the lifespan; the request passes its session alone
class AllotmentServiceFactory(Protocol):
    def __call__(
        self, *, plots: PlotRepository, transaction: AllotmentTransaction
    ) -> AllotmentService: ...


async def get_allotments(request: Request, session: GardenSessionDep) -> AllotmentService:
    build_allotments: AllotmentServiceFactory = request.state.build_allotments
    return build_allotments(plots=SqlPlotRepository(session=session), transaction=session)
```

### The request's session comes from a dependency with `scope="function"`, and repositories take it

**Why:** the exit of a dependency with `yield` runs after the response is sent — measured on
FastAPI 0.143, a streamed body went out before the dependency's `finally` — so the session and its
pooled connection stay out until the client has the whole response. `scope="function"` closes it as
soon as the route returns. The service is built per request on that session: its repositories take
the session, and the session is also its `AllotmentTransaction`.

**Example:**
```python
# WRONG — the default scope: the session holds its connection until the response has been sent
async def open_garden_session(request: Request) -> AsyncIterator[AsyncSession]:
    garden_sessions: async_sessionmaker[AsyncSession] = request.state.garden_sessions
    async with garden_sessions() as session:
        yield session


type GardenSessionDep = Annotated[AsyncSession, Depends(open_garden_session)]


# CORRECT — closed when the route returns; the repositories and the service share the session
async def open_garden_session(request: Request) -> AsyncIterator[AsyncSession]:
    garden_sessions: async_sessionmaker[AsyncSession] = request.state.garden_sessions
    async with garden_sessions() as session:
        yield session


type GardenSessionDep = Annotated[AsyncSession, Depends(open_garden_session, scope="function")]


async def get_allotments(request: Request, session: GardenSessionDep) -> AllotmentService:
    build_allotments: AllotmentServiceFactory = request.state.build_allotments
    return build_allotments(plots=SqlPlotRepository(session=session), transaction=session)


type AllotmentsDep = Annotated[AllotmentService, Depends(get_allotments)]
```

### The service commits; the dependency only closes the session

**Why:** a session opened with `garden_sessions.begin()` in the dependency commits on its way out,
so the use case no longer decides its own boundary: it cannot commit before a side effect, nor roll
back and re-run after a conflict. Closing a session the service did not commit rolls the request's
writes back, which is the answer to an error.

**Example:**
```python
# WRONG — the dependency commits, outside the use case that should decide it
async def open_garden_session(request: Request) -> AsyncIterator[AsyncSession]:
    garden_sessions: async_sessionmaker[AsyncSession] = request.state.garden_sessions
    async with garden_sessions.begin() as session:
        yield session


# CORRECT — the dependency closes; AllotmentService.release_plot commits as its last step
async def open_garden_session(request: Request) -> AsyncIterator[AsyncSession]:
    garden_sessions: async_sessionmaker[AsyncSession] = request.state.garden_sessions
    async with garden_sessions() as session:
        yield session
```

### A route takes the service, never the session

**Why:** a route that queries through the session is business logic in the HTTP layer, reachable
only through HTTP, and it is where the next write forgets to commit.

**Example:**
```python
# WRONG — the route reads and changes the row itself
@plots_router.post("/plots/{plot_id}/release")
async def release_plot(plot_id: PlotId, session: GardenSessionDep) -> PlotResponse:
    row = await session.get_one(PlotRow, plot_id)
    row.gardener_id = None
    return PlotResponse.from_row(row)


# CORRECT — the service owns the use case and its commit; the route converts and calls it
@plots_router.post("/plots/{plot_id}/release")
async def release_plot(plot_id: PlotId, allotments: AllotmentsDep) -> PlotResponse:
    return PlotResponse.from_domain(await allotments.release_plot(plot_id))
```
