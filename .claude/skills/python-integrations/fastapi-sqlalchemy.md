# FastAPI and SQLAlchemy

The seam between `python-fastapi` and `python-sqlalchemy`, linked from both skills. Where a
transaction begins and who commits it is `python-persistence`.

### The lifespan builds the engine and the session factory, and disposes the engine as it ends

**Why:** a module-level engine is opened at import and closed by nobody, so every worker's pool
outlives its shutdown and the database logs the connections as dropped; an engine built in a
dependency is a pool per request. The lifespan builds one and disposes it after the last request.

**Example:**
```python
# WRONG — the engine is opened at import and never disposed
_ENGINE: Final = create_async_engine(os.environ["DATABASE_URL"])


def create_app() -> FastAPI:
    app = FastAPI()
    app.state.session_factory = async_sessionmaker(_ENGINE, expire_on_commit=False)
    app.include_router(tasks_router)
    return app


# CORRECT — built when the app starts, disposed when it stops, whatever happened in between
def create_app(*, database: DatabaseConfig, max_attachment_bytes: int) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        engine = create_async_engine(
            database.url, pool_size=database.pool_size, pool_pre_ping=True
        )
        task_service_factory: TaskServiceFactory = partial(
            TaskService, max_attachment_bytes=max_attachment_bytes
        )
        try:
            yield {
                "session_factory": async_sessionmaker(engine, expire_on_commit=False),
                "task_service_factory": task_service_factory,
            }
        finally:
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.include_router(tasks_router)
    return app
```

### The lifespan binds fixed values into a service factory; a request adds its session

**Why:** a service holds two kinds of input: values fixed for the app's life, and a session, one per
request. A dependency that looks the values up to build the service on every request is the
configuration lookup the dependency rule forbids, and a service built once in the lifespan cannot
hold a session. `partial` splits them: the lifespan binds what is application-scoped once, and the
dependency passes only what is request-scoped. The factory is typed as a calling protocol: as
`partial[TaskService]` mypy accepts a call that omits the transaction — measured — while the
protocol checks both the binding in the lifespan and the call in the dependency.

**Example:**
```python
# WRONG — every request reads the limit from the state to build the service
async def get_task_service(request: Request, session: SessionDep) -> TaskService:
    max_attachment_bytes: int = request.state.max_attachment_bytes
    return TaskService(
        tasks=SqlTaskRepository(session),
        transaction=session,
        max_attachment_bytes=max_attachment_bytes,
    )


# CORRECT — the values were bound in the lifespan; the request passes its session alone
class TaskServiceFactory(Protocol):
    def __call__(self, *, tasks: TaskRepository, transaction: Transaction) -> TaskService: ...


async def get_task_service(request: Request, session: SessionDep) -> TaskService:
    build_task_service: TaskServiceFactory = request.state.task_service_factory
    return build_task_service(tasks=SqlTaskRepository(session), transaction=session)
```

### The request's session comes from a dependency with `scope="function"`, and repositories take it

**Why:** the exit of a dependency with `yield` runs after the response is sent — measured on
FastAPI 0.143, the body went out before the dependency's `finally` — so the session and its pooled
connection stay out until the client has the whole response, a stream's included.
`scope="function"` closes it as soon as the route returns. The service is built per request on that
session: its repositories take the session, and the session is also its `Transaction`.

**Example:**
```python
# WRONG — the default scope: the session holds its connection until the response has been sent
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.state.session_factory
    async with session_factory() as session:
        yield session


type SessionDep = Annotated[AsyncSession, Depends(get_session)]


# CORRECT — closed when the route returns; the repositories and the service share the session
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.state.session_factory
    async with session_factory() as session:
        yield session


type SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


async def get_task_service(request: Request, session: SessionDep) -> TaskService:
    build_task_service: TaskServiceFactory = request.state.task_service_factory
    return build_task_service(tasks=SqlTaskRepository(session), transaction=session)


type TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
```

### The service commits; the dependency only closes the session

**Why:** a session opened with `session_factory.begin()` in the dependency commits on its way out,
so the use case no longer decides its own boundary: it cannot commit before a side effect, nor roll
back and re-run after a conflict (`python-persistence`). Closing a session the service did not
commit rolls the request's writes back, which is the answer to an error.

**Example:**
```python
# WRONG — the dependency commits, outside the use case that should decide it
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.state.session_factory
    async with session_factory.begin() as session:
        yield session


# CORRECT — the dependency closes; TaskService.close commits as its last step
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.state.session_factory
    async with session_factory() as session:
        yield session
```

### A route takes the service, never the session

**Why:** a route that queries through the session is business logic in the HTTP layer, reachable
only through HTTP, and it is where the next write forgets to commit.

**Example:**
```python
# WRONG — the route reads and changes the row itself
@tasks_router.post("/tasks/{task_id}/close")
async def close_task(task_id: TaskId, session: SessionDep) -> TaskResponse:
    row = await session.get_one(TaskRow, task_id)
    row.status = TaskStatus.CLOSED
    return TaskResponse.from_row(row)


# CORRECT — the service owns the use case and its commit; the route converts and calls it
@tasks_router.post("/tasks/{task_id}/close")
async def close_task(task_id: TaskId, tasks: TaskServiceDep) -> TaskResponse:
    return TaskResponse.from_domain(await tasks.close(task_id))
```
