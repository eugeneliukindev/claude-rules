# Probes

### Liveness asks only whether the process answers; readiness asks about its dependencies

**Why:** a failed liveness probe restarts the container, a failed readiness probe takes it out of
the endpoints. If liveness checked the tile pyramid, its outage would restart every replica, over
and over, and no restart fixes the tile pyramid. The readiness check runs under a deadline shorter
than the probe's timeout; a slow start is a startup probe's job, not a long initial delay on
liveness.

**Example:**
```python
# WRONG — liveness asks the tile pyramid: while it is down, every replica restarts, over and over
async def liveness(*, pyramid: TilePyramid) -> HTTPStatus:
    await pyramid.ping()
    return HTTPStatus.NO_CONTENT


# CORRECT — liveness asks only whether the process answers; the tile pyramid decides readiness
async def liveness() -> HTTPStatus:
    return HTTPStatus.NO_CONTENT


async def readiness(
    *, pyramid: TilePyramid, deadline_seconds: float = _READINESS_DEADLINE_SECONDS
) -> HTTPStatus:
    try:
        async with asyncio.timeout(deadline_seconds):
            await pyramid.ping()
    except (TilePyramidUnavailableError, TimeoutError):
        return HTTPStatus.SERVICE_UNAVAILABLE
    return HTTPStatus.NO_CONTENT
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
