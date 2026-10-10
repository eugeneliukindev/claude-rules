---
name: python-container
description: >-
  Packaging a uv-managed Python service into a container image: a multi-stage Dockerfile with uv in
  the builder and only the virtual environment in the runtime, uv sync --locked
  --no-install-project in its own layer with a cache mount, UV_COMPILE_BYTECODE, UV_LINK_MODE and
  UV_PYTHON_DOWNLOADS=never, base images pinned by tag and digest, a numeric non-root user, an
  exec-form CMD so SIGTERM reaches Python, no uv run at runtime, the worker count against the CPU
  limit, migrations as a deploy step, build secrets through secret mounts, an allowlist
  .dockerignore, liveness versus readiness, a read-only root filesystem and image scanning. Use
  when writing or reviewing a Dockerfile, Containerfile, .dockerignore, compose file or health
  probe for a Python service, or deciding how a Python process starts and stops in a container.
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
the grace period is `python-workers`; settings are `python-wiring`; secrets in code are
`python-security`. This file covers what the image and its start command add. A one-off job runs
from the service's own image with a different command, so nothing here relaxes for a script.

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
CMD ["uvicorn", "--factory", "shop.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

## Two Stages, One Interpreter

- **The builder holds uv, the cache and the source; the runtime holds the interpreter and the
  virtual environment.** `--no-editable` installs the project into `site-packages` like any other
  dependency, so the runtime copies `/app/.venv` and nothing else. No source, no uv and no build
  tool is in the shipped image.
- **Both stages start from one image, named once.** The environment's `bin/python` is a symlink to
  the builder's interpreter, `/usr/local/bin/python3`, so the runtime must have the same interpreter
  at the same path. One `ARG` used by both `FROM` lines makes that structural, not something to
  remember.
- **The image's Python is the one CI tests, and it meets `requires-python`.** By default uv
  downloads a managed interpreter when the image's interpreter is too old. It lands under
  `/root/.local/share/uv/python` in the builder, the environment links to it, and the runtime never
  receives it. The build then passes and every start fails.

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

A managed interpreter can be a deliberate choice. In that case fix its location with
`UV_PYTHON_INSTALL_DIR` and copy that directory into the runtime as well.

## Dependencies Before Source

- **The lock is synced in a layer of its own, before the source is copied.** Docker reuses a layer
  until one of its inputs changes. If the dependencies are installed after `COPY .`, a one-line edit
  invalidates them. If they are installed with only `uv.lock` and `pyproject.toml` bind-mounted,
  the same edit reinstalls one package, the project.

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

- **`--locked`, never `--frozen`.** `--locked` fails when `uv.lock` no longer matches
  `pyproject.toml`. `--frozen` installs the stale lock without saying so. The image installs the
  lock CI tested (`python-project`). In a workspace, the first sync is the exception: it has only
  the lock and uses `--frozen --no-install-workspace`, and the second sync still checks with
  `--locked`.
- **`--no-dev` keeps the `dev` group out.** Anything the image runs is a runtime dependency. That
  includes the migration tool when migrations are run from this image (below).
- **The cache is a mount, not a layer.** It survives between builds and never ships. It sits on a
  different filesystem from `/app`, so uv cannot link from it; `UV_LINK_MODE=copy` makes uv copy
  instead of warning on every install.
- **`UV_COMPILE_BYTECODE=1` compiles once, at build time.** Without it, every start of every
  replica compiles each module it imports. On a read-only filesystem the result cannot be stored,
  so the work is repeated on every start.

## Pinned Base Images

- **A base image is named by tag and digest.** A tag can be moved to another image; the digest
  cannot. The tag stays for the reader and for the update bot. Pin the uv image the same way: it is
  a build input like the interpreter.

```dockerfile
# WRONG — two moving tags: the same commit builds a different image next week
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

# CORRECT — the version for the reader, the digest for the build
FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /bin/
```

- **A pinned digest is updated by a bot, or it is a pin on old vulnerabilities.** A moving tag at
  least picked up the base image's security fixes. A digest nobody updates keeps the vulnerabilities
  it was built with. Use an update bot that rewrites Docker digests, and rebuild on its pull
  requests even when the code has not changed.

## Running Unprivileged and Read-Only

- **`USER` is numeric, and the application cannot write its own files.** Kubernetes'
  `runAsNonRoot` can only check a number. For a name, the kubelet refuses to start the container
  with "image has non-numeric user (app), cannot verify user is non-root". `COPY` without `--chown`
  leaves the environment owned by root and readable by everyone, so the process runs its code but
  cannot rewrite it.
- **The image runs with a read-only root filesystem**, `docker run --read-only --tmpfs /tmp` or
  `readOnlyRootFilesystem: true` with an `emptyDir` on `/tmp`. Scratch files go through `tempfile`,
  which writes to `/tmp`. Anything that must outlive the container goes to a mounted volume or an
  external store. A write anywhere else fails in production on the first request that makes it, so
  run the image read-only in CI too.
- **`PYTHONUNBUFFERED=1`**: when stdout is not a terminal, it is block-buffered, and the last lines
  `print` wrote before a crash or a kill never arrive. Since 3.9, stderr is line-buffered, so
  `logging`'s default handler survives either way. The setting is for everything else that writes
  to stdout.
- **`PYTHONDONTWRITEBYTECODE=1`, in the runtime stage only.** The environment arrives compiled. The
  official image strips the standard library's `.pyc` files, and the non-root user cannot write to
  `/usr/local`. Every remaining write attempt would fail or land in a layer that dies with the
  container. Leave it out of the builder, where the compiling happens.

## Starting and Stopping

- **`CMD` and `ENTRYPOINT` use the exec form.** In shell form `/bin/sh -c` is PID 1, and `sh`
  does not forward `SIGTERM`. `docker stop` then waits ten seconds and sends `SIGKILL`. The
  lifespan never closes, and the graceful shutdown `python-async` designs never runs. The same
  happens with a single command, a `migrate && serve` chain, and a wrapper script that does not
  `exec`.

```dockerfile
# WRONG — /bin/sh is PID 1: the stop takes ten seconds and ends in SIGKILL, exit code 137
CMD uvicorn --factory shop.api:create_app --host 0.0.0.0 --port 8000

# CORRECT — uvicorn is PID 1, receives SIGTERM, closes the lifespan and exits 0
CMD ["uvicorn", "--factory", "shop.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

A wrapper script is allowed when its last line is `exec "$@"` or `exec uvicorn …`. `exec`
replaces the shell with the server, which then becomes PID 1.

- **PID 1 ignores every signal it has no handler for.** uvicorn and gunicorn install a `SIGTERM`
  handler. A worker you write must install its own, or the stop runs out the grace period and ends
  in `SIGKILL`. Handling only Ctrl-C is the version that passes on a laptop. `--init` and `tini`
  forward the signal, but then `SIGTERM`'s default action ends Python at once, without running any
  `finally`, so they do not replace a handler. The asyncio form is in `python-async`.

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

- **No `uv run` at runtime.** It does forward `SIGTERM`. But it syncs the environment again at
  every start: it reinstalled the project, as editable, over the `--no-editable` build. It needs uv
  in the image and a writable cache, and on a read-only root it fails with "Failed to initialize
  cache". The build already resolved everything, and `PATH` puts the environment's scripts first.
  uv's own multi-stage example also starts without uv.

```dockerfile
# WRONG — resolves and installs at start, ships uv, and fails on a read-only root
CMD ["uv", "run", "uvicorn", "--factory", "shop.api:create_app", "--host", "0.0.0.0", "--port", "8000"]

# CORRECT — the build resolved; the environment's bin directory is first on PATH
CMD ["uvicorn", "--factory", "shop.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

- **One process per container.** No supervisor, no `&`, and no cron beside the server. Each one
  hides the others' crashes from the orchestrator. A second process is a second container from the
  same image, with another command.
- **The worker count is a number, chosen next to the CPU limit.** `os.cpu_count()`,
  `os.process_cpu_count()` and `nproc` report the node's CPUs, not the container's limit: a
  container limited to one CPU on a sixteen-core node reads 16. gunicorn's documented starting point
  of (2 × cores) + 1 then means 33 processes sharing one CPU. Under an orchestrator, one worker per
  container and scaling by replicas is the default. Otherwise set `--workers`, or `WEB_CONCURRENCY`,
  which both uvicorn and gunicorn read. From 3.13, `PYTHON_CPU_COUNT` also overrides what the
  library defaults see, such as executor sizes.

## Migrations Are a Deploy Step

```dockerfile
# WRONG — every replica migrates at start, concurrently, and a failing migration is a crash loop
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn --factory shop.api:create_app --host 0.0.0.0 --port 8000"]

# CORRECT — the image only serves; the deploy runs the migration once, from the same image
CMD ["uvicorn", "--factory", "shop.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

The deploy runs the migration once, before the rollout: `docker run --rm IMAGE alembic upgrade
head`, or a Kubernetes `Job` from the same image and tag. An init container is not that step,
because it runs once per pod. The old replicas keep serving while the migration runs, which is why
the migration must be expand-first (`python-migrations`; the alembic mechanics are in
`python-alembic`).

## Configuration and Secrets

- **One image for every environment, configured at start.** Settings come from the environment
  when the process starts, and are validated before it serves (`python-wiring`). An `ENV
  DATABASE_URL` or a copied `.env` bakes one environment into the image, and the image then holds a
  credential in a layer. `ENV` is for facts about the image, such as `PATH` and the `PYTHON*` flags
  above.
- **A secret the build needs arrives as a secret mount, never as a build argument.** A build
  argument used by a `RUN` is recorded in the image history, and `docker history` prints it. A
  secret mount exists for one `RUN` and is written to no layer and no history. The credential for a
  private index named `private` is `UV_INDEX_PRIVATE_PASSWORD`. Every sync that resolves against
  that index needs it, the dependency layer included.

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

- **`.dockerignore` lists what enters, not what stays out.** The build context is everything the
  daemon receives. A denylist is right only until someone adds the next `.env`, key file or data
  dump. An allowlist fails closed. It also keeps out the local `.venv`, which is built for the host
  platform.

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

## Liveness and Readiness

When a liveness probe fails, the container is restarted. When a readiness probe fails, the
container is taken out of the service's endpoints. So the two endpoints ask different questions.
**Liveness asks only whether the process still answers.** **Readiness asks whether it can serve
right now**: its database, its cache, its warm-up. If liveness checked a dependency, an outage of
that dependency would restart every replica, over and over, and none of the restarts would fix the
dependency.

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
        await database.ping()
    except DatabaseUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from error
```

- **The readiness check runs under a deadline shorter than the probe's timeout.** Otherwise the
  probe times out first and reports nothing useful (`python-boundaries`). A slow start is a startup
  probe's job, not a long initial delay on liveness.
- **A gRPC service answers the kubelet's `grpc:` probe through the gRPC health service**, not an
  HTTP route (`python-grpc`).
- **`HEALTHCHECK` is for Docker and compose; Kubernetes runs the probes in the pod spec.** Where it
  is used, it calls liveness with the interpreter the image already has, under a timeout. Never
  install `curl` just for the health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/livez', timeout=2)"]
```

## Scanning

- **The built image is scanned in CI**, with Trivy, Grype or Docker Scout. The build fails on a
  high or critical finding that has a fix. Scanning the image covers the base image's operating
  system packages, which `pip-audit` (`python-security`) does not see.
- **The image is rebuilt on a schedule, not only on a commit.** A base-image fix reaches only
  images built after it.
- **The uv image's provenance can be checked** with `gh attestation verify --owner astral-sh
  oci://ghcr.io/astral-sh/uv:0.13.0` before its digest is pinned.
