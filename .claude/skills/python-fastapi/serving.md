# Serving With uvicorn

The drain at shutdown and the WebSocket limits are in [streaming.md](streaming.md); the container
start command is `python-container`.

### Behind a proxy, `--forwarded-allow-ips` names the proxy's network

**Why:** the default is `127.0.0.1,::1`, so behind an ingress every request appears to come from the
ingress and rate limits and audit logs see one client; `*` lets any caller forge its address.
