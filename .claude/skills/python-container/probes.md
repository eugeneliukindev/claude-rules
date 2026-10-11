# Probes

### Liveness asks only whether the process answers; readiness asks about its dependencies

**Why:** a failed liveness probe restarts the container, a failed readiness probe takes it out of
the endpoints. If liveness checked the database, an outage would restart every replica, over and
over, and no restart fixes the database. The readiness check runs under a deadline shorter than the
probe's timeout (`python-boundaries`); a slow start is a startup probe's job, not a long initial
delay on liveness.

**Example:**
```python
# WRONG — liveness asks the database: while it is down, every replica is restarted, over and over
@health_router.get("/livez", status_code=status.HTTP_204_NO_CONTENT)
async def report_liveness(database: DatabaseDep) -> None:
    await database.ping()


# CORRECT — liveness asks only whether the process answers; the database decides readiness
@health_router.get("/livez", status_code=status.HTTP_204_NO_CONTENT)
async def report_liveness() -> None:
    """Answer while the event loop serves requests."""


@health_router.get("/readyz", status_code=status.HTTP_204_NO_CONTENT)
async def report_readiness(database: DatabaseDep) -> None:
    try:
        async with asyncio.timeout(_READINESS_DEADLINE_SECONDS):
            await database.ping()
    except (DatabaseUnavailableError, TimeoutError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from error
```

### `HEALTHCHECK`, where Docker or compose runs it, calls liveness with the image's own interpreter

**Why:** Kubernetes runs the probes in the pod spec and ignores `HEALTHCHECK`; where it is used,
installing `curl` for it adds a package and its vulnerabilities to every image.

**Example:**
```dockerfile
# WRONG — a package installed only for the health check
RUN apt-get update && apt-get install --yes --no-install-recommends curl
HEALTHCHECK CMD curl --fail http://127.0.0.1:8000/livez

# CORRECT — the interpreter the image already has, under a timeout
HEALTHCHECK --interval=30s --timeout=3s \
    CMD ["python", "-c", \
         "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/livez', timeout=2)"]
```
