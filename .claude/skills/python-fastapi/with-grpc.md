# FastAPI With a gRPC Server

How the server is built, drained and stopped is `python-grpc`.

### Beside FastAPI, the gRPC server lives in the lifespan, and the app runs one worker

**Why:** one process, one deploy, one shutdown. Measured under uvicorn: on `SIGTERM`, new gRPC calls
were refused with `UNAVAILABLE`, the call in flight finished inside the grace, and the process
exited 0. Every uvicorn worker runs the lifespan: with `--workers 2` the second failed to bind and
uvicorn stopped, and with the reuse-port default it would have shared the port silently. When the
gRPC side scales apart from HTTP, or HTTP needs several workers, the server runs as a second entry
point in the same image, in a second container.

**Example:**
```python
# WRONG — started as a task the lifespan never stops: no drain, and an error in it goes unseen
def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_task_store(settings.database_url) as store:
            tasks = TaskService(tasks=store)
            asyncio.create_task(serve(tasks=tasks, address=settings.grpc_address))
            yield {"task_service": tasks}

    app = FastAPI(lifespan=lifespan)
    app.include_router(tasks_router)
    return app


# CORRECT — the server is entered inside the store and left before it, drained on the way out
def create_app(settings: Settings) -> FastAPI:
    grpc_credentials = grpc.ssl_server_credentials(
        [(settings.grpc_private_key.get_secret_value(), settings.grpc_certificate_chain)]
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_task_store(settings.database_url) as store:
            tasks = TaskService(tasks=store)
            async with managed_grpc_server(
                tasks=tasks,
                address=settings.grpc_address,
                credentials=grpc_credentials,
                grace_seconds=settings.grpc_grace_seconds,
            ):
                yield {"task_service": tasks}

    app = FastAPI(lifespan=lifespan)
    app.include_router(tasks_router)
    return app
```
