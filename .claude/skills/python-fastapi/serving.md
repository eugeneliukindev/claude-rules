# Serving With uvicorn

The WebSocket limits are in [streaming.md](streaming.md); the container start command is
`python-container`.

### The entry point builds the settings and runs uvicorn with the app; the app reads no environment

**Why:** `uvicorn --factory` calls a function with no arguments, so the app module would have to
read the environment itself — the one place allowed to read it is the entry point, which builds the
settings once and unpacks the fields `create_app` takes. It runs `uvicorn.Server` with that app, the
server's options from the same settings; tests call `create_app` with their own values.

**Example:**
```python
# WRONG — `uvicorn --factory tracker.api:app_from_environment`: the app module reads the environment
def app_from_environment() -> FastAPI:
    settings = Settings()
    return create_app(database_url=settings.database_url)


# CORRECT — `tracker-server = "tracker.server:main"`: the entry point reads, the app receives
def main() -> None:
    settings = Settings()
    config = uvicorn.Config(
        create_app(database_url=settings.database_url), host=settings.host, port=settings.port
    )
    uvicorn.Server(config).run()
```

### The drain is bounded with `timeout_graceful_shutdown`, a few seconds below the grace period

**Why:** without it uvicorn waits for every open request on `SIGTERM`, and one stream outlives the
orchestrator's grace period into `SIGKILL`, so the lifespan's shutdown never runs.

**Example:**
```python
# WRONG — the drain waits for every open request
def main() -> None:
    settings = Settings()
    config = uvicorn.Config(
        create_app(database_url=settings.database_url), host=settings.host, port=settings.port
    )
    uvicorn.Server(config).run()


# CORRECT — open requests get the drain, inside Kubernetes' default 30 seconds, then the lifespan
def main() -> None:
    settings = Settings()
    config = uvicorn.Config(
        create_app(database_url=settings.database_url),
        host=settings.host,
        port=settings.port,
        timeout_graceful_shutdown=settings.drain_seconds,
    )
    uvicorn.Server(config).run()
```

### Behind a proxy, `forwarded_allow_ips` names the proxy's network

**Why:** the default is `127.0.0.1,::1`, so behind an ingress every request appears to come from the
ingress and rate limits and audit logs see one client; `*` lets any caller forge its address.
