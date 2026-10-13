# FastAPI and gRPC

The seam between `python-fastapi` and `python-grpc`, linked from both skills.

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
def create_app(*, database_url: str, grpc_server: GrpcServerConfig) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_task_store(database_url) as store:
            tasks = TaskService(tasks=store)
            asyncio.create_task(serve(tasks=tasks, address=grpc_server.address))
            yield {"task_service": tasks}

    app = FastAPI(lifespan=lifespan)
    app.include_router(tasks_router)
    return app


# CORRECT — the server is entered inside the store and left before it, drained on the way out
def create_app(*, database_url: str, grpc_server: GrpcServerConfig) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_task_store(database_url) as store:
            tasks = TaskService(tasks=store)
            async with managed_grpc_server(
                tasks=tasks,
                address=grpc_server.address,
                credentials=grpc.ssl_server_credentials(
                    [(grpc_server.private_key, grpc_server.certificate_chain)]
                ),
                grace_seconds=grpc_server.grace_seconds,
            ):
                yield {"task_service": tasks}

    app = FastAPI(lifespan=lifespan)
    app.include_router(tasks_router)
    return app
```
