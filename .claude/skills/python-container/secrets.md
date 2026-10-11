# Configuration and Secrets

### One image serves every environment; a build-time secret is a secret mount

**Why:** settings come from the environment at start and are validated before serving
(`python-wiring`); an `ENV DATABASE_URL` or a copied `.env` bakes one environment in and holds a
credential in a layer. `ENV` is for facts about the image — `PATH`, the `PYTHON*` flags. A build
argument used by a `RUN` is recorded in the image history, which `docker history` prints; a secret
mount exists for one `RUN` and is written nowhere. The credential for a private index named
`private` is `UV_INDEX_PRIVATE_PASSWORD`, and every sync against that index needs it.

**Example:**
```dockerfile
# WRONG — the history records "RUN |1 UV_INDEX_PRIVATE_PASSWORD=<the password> ..."
ARG UV_INDEX_PRIVATE_PASSWORD
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# CORRECT — built with: docker build --secret id=index_password,env=INDEX_PASSWORD .
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=index_password,env=UV_INDEX_PRIVATE_PASSWORD,required=true \
    uv sync --locked --no-dev --no-editable
```

### `.dockerignore` lists what enters the context, not what stays out

**Why:** the context is everything the daemon receives; a denylist holds only until someone adds the
next `.env`, key file or data dump, where an allowlist fails closed. It also keeps out the local
`.venv`, built for the host platform.

**Example:**
```text
# WRONG — what to leave out: the .env nobody listed enters the context and the builder's layers
.venv
.git
__pycache__

# CORRECT — nothing enters but what the build reads; README.md because pyproject.toml names it
*
!pyproject.toml
!uv.lock
!README.md
!src/
**/__pycache__
```
