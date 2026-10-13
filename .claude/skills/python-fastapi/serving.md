# Serving With uvicorn

The WebSocket limits are in [streaming.md](streaming.md); the container
start command is `python-container`.

### The drain is bounded with `--timeout-graceful-shutdown`, a few seconds below the grace period

**Why:** without it uvicorn waits for every open request on `SIGTERM`, and one stream outlives the
orchestrator's grace period into `SIGKILL`, so the lifespan's shutdown never runs.

**Example:**
```bash
# WRONG — the drain waits for every open request
uvicorn --factory tracker.api:create_app --host 0.0.0.0 --port 8000

# CORRECT — open requests get 25 seconds, inside Kubernetes' default 30, then the lifespan closes
uvicorn --factory tracker.api:create_app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 25
```

### Behind a proxy, `--forwarded-allow-ips` names the proxy's network

**Why:** the default is `127.0.0.1,::1`, so behind an ingress every request appears to come from the
ingress and rate limits and audit logs see one client; `*` lets any caller forge its address.
