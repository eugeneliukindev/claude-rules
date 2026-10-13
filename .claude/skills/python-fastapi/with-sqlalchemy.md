# FastAPI With SQLAlchemy

How SQLAlchemy is used is `python-sqlalchemy`; where a transaction begins is `python-persistence`.

### The lifespan builds the engine and the session factory, and disposes the engine as it ends

**Why:** a module-level engine is opened at import and closed by nobody, so every worker's pool
outlives its shutdown and the database logs the connections as dropped; an engine built in a
dependency is a pool per request. The lifespan builds one, hands the session factory to the
adapters, and disposes it after the last request.

**Example:**
```python
# WRONG — the engine is opened at import and never disposed
_ENGINE: Final = create_async_engine(os.environ["DATABASE_URL"])


def create_app() -> FastAPI:
    app = FastAPI()
    app.state.task_service = TaskService(tasks=SqlTaskStore(async_sessionmaker(_ENGINE)))
    app.include_router(tasks_router)
    return app


# CORRECT — built when the app starts, disposed when it stops, whatever happened in between
def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        engine = create_async_engine(
            settings.database_url, pool_size=settings.database_pool_size, pool_pre_ping=True
        )
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            yield {"task_service": TaskService(tasks=SqlTaskStore(session_factory))}
        finally:
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.include_router(tasks_router)
    return app
```

### A route never takes an `AsyncSession` through `Depends`

**Why:** a session per request moves the transaction out of the service into the framework: the
commit happens after the route returns, outside the use case that should decide it, and a
streaming response holds the connection until the client leaves. The route takes the service; the
service's store opens and commits its own transaction.

**Example:**
```python
# WRONG — the route queries through a request-scoped session the framework commits later
@tasks_router.post("/tasks/{task_id}/close")
async def close_task(
    task_id: TaskId, session: Annotated[AsyncSession, Depends(get_session)]
) -> TaskResponse:
    row = await session.get_one(TaskRow, task_id)
    row.status = TaskStatus.CLOSED
    return TaskResponse.from_row(row)


# CORRECT — the service owns the transaction; the route converts and calls it
@tasks_router.post("/tasks/{task_id}/close")
async def close_task(task_id: TaskId, tasks: TaskServiceDep) -> TaskResponse:
    return TaskResponse.from_domain(await tasks.close(task_id))
```
