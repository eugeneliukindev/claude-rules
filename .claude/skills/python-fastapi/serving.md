# Serving With uvicorn

The drain at shutdown and the WebSocket limits are in [streaming.md](streaming.md); the container
start command is `python-container`.

### Behind a proxy, `--forwarded-allow-ips` names the proxy's network

**Why:** the default is `127.0.0.1,::1`, so behind an ingress every request appears to come from the
ingress and rate limits and audit logs see one client; `*` lets any caller forge its address.

**Example:**
```bash
# WRONG — the ingress is not 127.0.0.1: its X-Forwarded-For is ignored, every client is the ingress
uvicorn --factory tracker.api:create_app --host 0.0.0.0 --port 8000

# CORRECT — the forwarded address is believed from the ingress network, and from nowhere else
uvicorn --factory tracker.api:create_app --host 0.0.0.0 --port 8000 --forwarded-allow-ips 10.0.0.0/8
```
