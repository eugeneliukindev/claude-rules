# Upgrades and Audits

### The lock moves on purpose, in a commit of its own

**Why:** a lock refreshed inside a feature change hides which of the two broke the build, and a
revert of the feature takes the upgrade with it. `uv lock --upgrade-package NAME` moves one package,
`uv lock --upgrade` all of them; `uv tree --outdated` lists what is behind.

### A lower bound is tested by a CI job that installs every direct dependency at its floor

**Why:** a `pydantic>=2.11` that quietly needs 2.12 passes every run on the locked, newest versions
and fails on a user's machine. `--resolution lowest-direct` rewrites `uv.lock` — measured on uv 0.12
— so the job runs on a checkout it throws away, never before a commit.

**Example:**
```bash
# WRONG — the floor is declared and never installed; only the locked, newest versions are tested
uv sync --locked && uv run pytest

# CORRECT — a second CI job installs each direct dependency at its floor and runs the same suite
uv sync --resolution lowest-direct && uv run pytest
```

### `pip-audit` reads the lock's export, not the environment it runs in

**Why:** run with no arguments, `pip-audit` audits the environment of the interpreter running it;
under `uvx` that is its own tool environment — measured: 28 packages and "No known vulnerabilities
found" in a project locking `requests==2.25.0`, whose export reports four `urllib3` advisories.
Exported from the lock with hashes, `--disable-pip` checks exactly the versions that ship, without
installing them. Vulnerabilities in the image's operating system packages are a container scan's
(`python-container`).

**Example:**
```bash
# WRONG — audits pip-audit's own tool environment, not the project
uvx pip-audit

# CORRECT — the locked runtime dependencies, hashed, audited without an install
uv export --locked --no-dev --no-emit-project --format requirements-txt \
    --output-file requirements.txt
uvx pip-audit --disable-pip --requirement requirements.txt
```
