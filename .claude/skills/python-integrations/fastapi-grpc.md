# FastAPI and gRPC

The seam between `python-fastapi` and `python-grpc`, linked from both skills.

### Beside FastAPI, the gRPC server lives in the lifespan, and the app runs one worker

**Why:** one process, one deploy, one shutdown. Measured under uvicorn: on `SIGTERM`, new gRPC calls
were refused with `UNAVAILABLE`, the call in flight finished inside the grace, and the process
exited 0. Every uvicorn worker runs the lifespan: with `--workers 2` the second failed to bind and
uvicorn stopped, and with `grpc.so_reuseport` on it would have shared the port silently. When the
gRPC side scales apart from HTTP, or HTTP needs several workers, the server runs as a second entry
point in the same image, in a second container.

**Example:**
```python
# WRONG — started as a task the lifespan never stops: no drain, and an error in it goes unseen
def build_biobank_api(
    *,
    database_url: str,
    grpc_address: str,
    grpc_credentials: grpc.ServerCredentials,
    grpc_shutdown_grace_seconds: float = _GRPC_SHUTDOWN_GRACE_SECONDS,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with SampleStore.connect(database_url) as samples:
            biobank = BiobankService(samples=samples)
            asyncio.create_task(
                serve_samples(biobank=biobank, address=grpc_address, credentials=grpc_credentials)
            )
            yield {"biobank": biobank}

    app = FastAPI(lifespan=lifespan)
    app.include_router(samples_router)
    return app


# CORRECT — the server is entered inside the store and left before it, drained on the way out
def build_biobank_api(
    *,
    database_url: str,
    grpc_address: str,
    grpc_credentials: grpc.ServerCredentials,
    grpc_shutdown_grace_seconds: float = _GRPC_SHUTDOWN_GRACE_SECONDS,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with SampleStore.connect(database_url) as samples:
            biobank = BiobankService(samples=samples)
            async with sample_server_port(
                biobank=biobank,
                address=grpc_address,
                credentials=grpc_credentials,
                shutdown_grace_seconds=grpc_shutdown_grace_seconds,
            ):
                yield {"biobank": biobank}

    app = FastAPI(lifespan=lifespan)
    app.include_router(samples_router)
    return app
```
