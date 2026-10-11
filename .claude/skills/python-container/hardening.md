# Hardening

### The image runs as a numeric user that cannot write its own files, on a read-only root

**Why:** Kubernetes' `runAsNonRoot` can only check a number — for a name the kubelet refuses with
"image has non-numeric user (app), cannot verify user is non-root". `COPY` without `--chown` leaves
the environment owned by root, so the process runs its code but cannot rewrite it. With
`readOnlyRootFilesystem: true` and an `emptyDir` on `/tmp`, scratch files go through `tempfile` and
anything lasting goes to a volume or a store; a write anywhere else fails on the first request that
makes it, so CI runs the image read-only too.

**Example:**
```dockerfile
# WRONG — a named user, and the environment owned by it: the process can rewrite its own code
RUN useradd --system app
COPY --from=builder --chown=app /app/.venv /app/.venv
USER app

# CORRECT — a numeric user, and the environment left owned by root
RUN groupadd --system --gid 10001 app \
 && useradd --system --gid 10001 --uid 10001 --no-create-home app
COPY --from=builder /app/.venv /app/.venv
USER 10001
```

### The runtime sets `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`; the builder neither

**Why:** when stdout is not a terminal it is block-buffered, and the last lines `print` wrote before
a crash never arrive; stderr is line-buffered since 3.9, so `logging`'s default handler survives
either way. The environment arrives compiled and the non-root user cannot write to `/usr/local`, so
every remaining bytecode write would fail or land in a layer that dies with the container — but the
builder is where the compiling happens.

**Example:**
```dockerfile
# WRONG — the builder told not to write bytecode, so UV_COMPILE_BYTECODE's work is undone
FROM ${PYTHON_IMAGE} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1

# CORRECT — the runtime alone: unbuffered stdout, no bytecode writes that cannot succeed
FROM ${PYTHON_IMAGE}
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
```
