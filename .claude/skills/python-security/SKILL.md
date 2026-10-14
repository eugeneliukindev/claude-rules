---
name: python-security
description: >-
  Handles input from outside the process: secrets and tokens, password hashing, parameterized SQL,
  subprocess arguments, safe parsers, path traversal, archives, SSRF, size limits, failing closed.
  Use when code handles a request body, a filename, a URL, an upload, an archive, a subprocess
  argument, a credential or any untrusted payload. Not for tokens and permissions (python-auth).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Security

Input from outside the process, whatever library reads it. The rules name the function, because the
function is what gets copied. Where a secret lives is `python-wiring`; keeping it out of a `repr`
and a `LiteralString` check are `python-types`; verifying a bearer token and who may touch which
resource are `python-auth`; a WebSocket's `Origin` check is `python-streaming`; dependency scanning
is `python-project`; an exception escaping a gRPC handler is `python-grpc`.

## Untrusted Data

### SQL is parameterized, and an identifier comes from an allowlist of constants

**Why:** a value interpolated into SQL text writes SQL; an `ORDER BY` column or a table name cannot
be a bound parameter, so it is one of a fixed set of constants. A list of values is one parameter
too, never a joined string.

**Example:**
```python
# WRONG — the sort column arrives from the query string, so the query string writes SQL
def queued_print_jobs(
    press_id: int, *, connection: sqlite3.Connection, sort_by: str
) -> list[tuple[int, str]]:
    query = f"SELECT job_id, title FROM print_jobs WHERE press_id = ? ORDER BY {sort_by}"
    return connection.execute(query, (press_id,)).fetchall()


# CORRECT — the clause is one of two constants; only the value travels as a parameter
_PRINT_JOB_ORDER: Final = MappingProxyType(
    {PrintJobSort.NEWEST: "queued_at DESC", PrintJobSort.OLDEST: "queued_at ASC"}
)


def queued_print_jobs(
    press_id: int, *, connection: sqlite3.Connection, sort_by: PrintJobSort
) -> list[tuple[int, str]]:
    order_clause = _PRINT_JOB_ORDER[sort_by]
    query = (
        "SELECT job_id, title FROM print_jobs WHERE press_id = ?"
        f" ORDER BY {order_clause}"  # noqa: S608  # allowlisted identifier
    )
    return connection.execute(query, (press_id,)).fetchall()
```

### An untrusted document is parsed by the safe parser, and nothing from outside is evaluated

**Why:** `yaml.load(..., Loader=yaml.Loader)` calls whatever a `!!python/object/apply` tag names,
and `FullLoader` — which refuses those tags — still resolves `!!python/name` references to anything
already imported, a surface `safe_load` does not have. XML goes through `defusedxml`, which refuses
entity expansion and external entities. No `eval`, `exec` or `pickle.loads` on outside data;
`ast.literal_eval` when the input really is a Python literal.

### Every external input is bounded in size, decompression included

**Why:** validation includes size, not just shape — a body, a page, a collection, a decompressed
stream. Deflate packs about a thousand to one, so a megabyte of gzip becomes a gigabyte in memory.
A stream cut short inflates without an error — half a gzip payload returned 4 bytes of 10,023 and
`eof` stayed `False` — so the prefix would be handed on as the whole document without the last
check.

**Example:**
```python
# WRONG — inflates whatever the artwork expands to
def inflate_artwork(compressed: bytes) -> bytes:
    return gzip.decompress(compressed)


# CORRECT — inflate at most one byte past the limit, refuse that, and refuse a truncated stream
def inflate_artwork(compressed: bytes, *, max_bytes: int = _MAX_ARTWORK_BYTES) -> bytes:
    inflater = zlib.decompressobj(wbits=_GZIP_WBITS)
    artwork = inflater.decompress(compressed, max_bytes + 1)
    if len(artwork) > max_bytes:
        raise ArtworkTooLargeError(max_bytes)
    if not inflater.eof:
        raise TruncatedArtworkError(len(compressed))
    return artwork
```

## Decisions That Fail Closed

### A permission check allows what it lists, and an error inside it denies

**Why:** a check that denies a list of roles allows every role added after it; one that allows a
list denies them. A lookup that fails inside the check — the store holding the roles times out —
raises or denies, and nothing catches it into an allow.

**Example:**
```python
# WRONG — denies the roles it lists, so a role added next year may sign off any proof
def can_approve_proof(operator: PressOperator) -> bool:
    return operator.role not in _ROLES_WITHOUT_PROOF_APPROVAL


# CORRECT — allows the roles it lists; every other role, a new one included, is denied
def can_approve_proof(operator: PressOperator) -> bool:
    return operator.role in _PROOF_APPROVING_ROLES
```

### A secret is compared with `hmac.compare_digest`, never `==`

**Why:** `==` stops at the first differing byte, so the response time tells an attacker how much of
a guessed signature was right.

## Passwords

**Before storing or checking a password, read [passwords.md](passwords.md)** — Argon2id, or scrypt
with every parameter and `maxmem` stated.

## Paths, Uploads and Archives

**Before building a path from outside input, storing an upload, or extracting an archive, read
[paths.md](paths.md)** — resolve then compare components, a generated storage name, the `data`
extraction filter.

## URLs From Outside

**Before fetching a URL a user supplied, read [ssrf.md](ssrf.md)** — an allowlist checked against
the resolved addresses, and every redirect checked before it is followed.
