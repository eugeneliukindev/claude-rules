---
name: python-container
description: >-
  Packages a uv-managed Python service into a container image and runs it: a multi-stage
  Dockerfile, layers and caches, pinned base images, a non-root user, signals, workers, probes,
  secrets. Use when writing or reviewing a Dockerfile, Containerfile, .dockerignore, compose file
  or health probe for a Python service.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/Dockerfile*"
  - "**/Containerfile"
  - "**/.dockerignore"
  - "**/compose*.yml"
  - "**/compose*.yaml"
---

# Containers

Checked against uv 0.13.0 and Docker 29 with BuildKit. The project inside the image is
`python-project`'s; how the process shuts down is `python-async`, and how a consumer drains within
the grace period is `python-workers`; settings are `python-wiring`; the schema change a deploy runs
is `python-migrations`, with alembic's command in `python-alembic`; a gRPC service's health probe is
`python-grpc`; uvicorn's own flags are `python-fastapi`. A one-off job runs from the service's own
image with a different command, so nothing here relaxes for a script.

## The Image

Every rule below is a line of this file:

```dockerfile
# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE}
RUN groupadd --system --gid 10001 app \
 && useradd --system --gid 10001 --uid 10001 --no-create-home app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER 10001
WORKDIR /app
EXPOSE 8000
CMD ["uvicorn", "--factory", "tracker.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

### The builder holds uv and the source; the runtime holds the same interpreter and the environment

**Why:** `--no-editable` installs the project into `site-packages`, so the runtime copies
`/app/.venv` and nothing else — no source, no uv, no build tool ships. The environment's
`bin/python` is a symlink to the builder's interpreter, so both stages start from one image named
once in an `ARG`. By default uv downloads a managed interpreter when the image's is too old; it
lands in the builder, the environment links to it, the runtime never receives it — the build passes
and every start fails. `UV_PYTHON_DOWNLOADS=never` turns that into a failed build; a deliberate
managed interpreter fixes `UV_PYTHON_INSTALL_DIR` and is copied too.

**Example:**
```dockerfile
# WRONG — downloads allowed: with a 3.13 floor on a 3.12 image the build passes, and the container
# fails with "exec /app/.venv/bin/uvicorn: no such file or directory"
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# CORRECT — the image's interpreter or a failed build: "No interpreter found for Python >=3.13"
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
```

### The lock is synced in a layer of its own, before the source, with `--locked` and `--no-dev`

**Why:** installed after `COPY .`, a one-line edit reinstalls every dependency; with only the lock
and `pyproject.toml` bind-mounted, the same edit reinstalls the project alone. `--locked` fails when
the lock no longer matches `pyproject.toml`, where `--frozen` installs the stale lock silently — in
a workspace the first sync alone uses `--frozen --no-install-workspace`. `--no-dev` keeps the `dev`
group out, so anything the image runs, the migration tool included, is a runtime dependency. The uv
cache is a mount, not a layer; it sits on another filesystem, so `UV_LINK_MODE=copy`.
`UV_COMPILE_BYTECODE=1` compiles once at build time instead of on every start of every replica.

**Example:**
```dockerfile
# WRONG — the source is an input of the only sync: any edit reinstalls every dependency
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# CORRECT — the dependency layer depends on the lock alone, and a source edit reuses it
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable
```

### A base image is pinned by tag and digest, and a bot keeps the digest current

**Why:** a tag can move to another image, a digest cannot; the tag stays for the reader and the
update bot. The uv image is a build input like the interpreter. A digest nobody updates keeps the
vulnerabilities it was built with, so a bot rewrites it and the image is rebuilt on its pull
requests even when the code has not changed.

**Example:**
```dockerfile
# WRONG — two moving tags: the same commit builds a different image next week
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

# CORRECT — the version for the reader, the digest for the build
FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /bin/
```

## Starting and Stopping

### `CMD` uses the exec form, so the server is PID 1 and receives `SIGTERM`

**Why:** in shell form `/bin/sh -c` is PID 1 and does not forward `SIGTERM`; `docker stop` waits ten
seconds and sends `SIGKILL`, the lifespan never closes, and the shutdown `python-async` designs
never runs — with a single command, a `migrate && serve` chain, or a wrapper script that does not
`exec`. A wrapper is allowed when its last line is `exec "$@"`.

**Example:**
```dockerfile
# WRONG — /bin/sh is PID 1: the stop takes ten seconds and ends in SIGKILL, exit code 137
CMD uvicorn --factory tracker.api:create_app --host 0.0.0.0 --port 8000

# CORRECT — the server is PID 1, receives SIGTERM, closes the lifespan and exits 0
CMD ["uvicorn", "--factory", "tracker.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

### A process you write handles `SIGTERM` itself, because PID 1 ignores what it does not handle

**Why:** uvicorn and gunicorn install a `SIGTERM` handler; a worker you write must install its own,
or the stop runs out the grace period into `SIGKILL`. Handling only Ctrl-C is the version that
passes on a laptop. `--init` and `tini` forward the signal, but then `SIGTERM`'s default action ends
Python without running any `finally`, so they replace no handler.

**Example:**
```python
# WRONG — Ctrl-C is handled and SIGTERM is not: as PID 1 the stop is ignored until SIGKILL
def main() -> None:
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda _signal_number, _frame: stop.set())
    with build_consumer() as consumer:
        consumer.run_until(stop)


# CORRECT — both signals set the event; the consumer stops and the with block closes it
def main() -> None:
    stop = threading.Event()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signal_number, lambda _signal_number, _frame: stop.set())
    with build_consumer() as consumer:
        consumer.run_until(stop)
```

### The server's drain is bounded a few seconds below the orchestrator's grace period

**Why:** on `SIGTERM` an HTTP server stops accepting and waits for open requests — without a bound,
one stream or slow client runs Kubernetes' default thirty seconds into `SIGKILL`, and the lifespan's
shutdown never runs. uvicorn's flag for it is `--timeout-graceful-shutdown`.

**Example:**
```dockerfile
# WRONG — the drain waits for every open request; a stream outlives the grace period
CMD ["uvicorn", "--factory", "tracker.api:create_app", "--host", "0.0.0.0", "--port", "8000"]

# CORRECT — open requests get 25 seconds, inside the default 30, then the lifespan closes
CMD ["uvicorn", "--factory", "tracker.api:create_app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "25"]
```

### The image starts its server directly, never through `uv run`

**Why:** `uv run` syncs the environment again at every start — it reinstalled the project, as
editable, over the `--no-editable` build — needs uv in the image and a writable cache, and on a
read-only root fails with "Failed to initialize cache". The build already resolved everything, and
`PATH` puts the environment's scripts first.

**Example:**
```dockerfile
# WRONG — resolves and installs at start, ships uv, and fails on a read-only root
CMD ["uv", "run", "uvicorn", "--factory", "tracker.api:create_app", "--host", "0.0.0.0", \
     "--port", "8000"]

# CORRECT — the build resolved; the environment's bin directory is first on PATH
CMD ["uvicorn", "--factory", "tracker.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

## Hardening

**Before choosing the image's user, its filesystem or its `PYTHON*` variables, read
[hardening.md](hardening.md)** — a numeric `USER`, a read-only root, `PYTHONUNBUFFERED`,
`PYTHONDONTWRITEBYTECODE` in the runtime only.

## Processes and Workers

**Before adding a second process to a container or setting the worker count, read
[processes.md](processes.md)** — one process per container, the count chosen beside the CPU limit.

## Migrations

**Before deciding where the schema migration runs, read [migrations.md](migrations.md)** — a deploy
step from the same image, never at start.

## Configuration and Secrets

**Before putting configuration, a credential or a `.dockerignore` into the build, read
[secrets.md](secrets.md)** — one image for every environment, a secret mount instead of a build
argument, an allowlist context.

## Probes

**Before writing a liveness or readiness endpoint, a `HEALTHCHECK` or a probe, read
[probes.md](probes.md)** — liveness asks only whether the process answers, readiness asks about
dependencies under a deadline.

## Scanning

**Before setting up the image's CI, read [scanning.md](scanning.md)** — an image scan that fails the
build, scheduled rebuilds, the uv image's provenance.
