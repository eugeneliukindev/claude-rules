---
name: python-security
description: >-
  Handles input from outside the process: secrets and tokens, password hashing, parameterized SQL,
  subprocess arguments, safe parsers, path traversal, archives, SSRF, size limits, failing closed.
  Use when code handles a request body, a filename, a URL, an upload, an archive, a subprocess
  argument, a credential or any untrusted payload.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Security

Input from outside the process, whatever library reads it. The rules name the function, because the
function is what gets copied. Where a secret lives is `python-wiring`, and keeping it out of a
`repr` is `python-types`; verifying a bearer token and IDOR are `python-auth`; a WebSocket's
`Origin` check is `python-streaming`; a `LiteralString` check under pyright is `python-types`;
dependency scanning is `python-project`; an exception escaping a gRPC handler is `python-grpc`.

## Untrusted Data

### SQL is parameterized, and an identifier comes from an allowlist of constants

**Why:** a value interpolated into SQL text writes SQL; an `ORDER BY` column or a table name cannot
be a bound parameter, so it is one of a fixed set of constants. A list of values is one parameter
too, never a joined string.

**Example:**
```python
# WRONG — the sort column arrives from the query string, so the query string writes SQL
def open_tickets(*, connection: sqlite3.Connection, queue_id: int, sort_by: str) -> list[Row]:
    query = f"SELECT ticket_id, subject FROM tickets WHERE queue_id = ? ORDER BY {sort_by}"
    return connection.execute(query, (queue_id,)).fetchall()


# CORRECT — the clause is one of two constants; only the value travels as a parameter
_ORDER_BY: Final = MappingProxyType(
    {TicketSort.NEWEST: "opened_at DESC", TicketSort.OLDEST: "opened_at ASC"}
)


def open_tickets(
    *, connection: sqlite3.Connection, queue_id: int, sort_by: TicketSort
) -> list[Row]:
    order_by = _ORDER_BY[sort_by]
    query = (
        "SELECT ticket_id, subject FROM tickets WHERE queue_id = ?"
        f" ORDER BY {order_by}"  # noqa: S608  # allowlisted identifier
    )
    return connection.execute(query, (queue_id,)).fetchall()
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
# WRONG — inflates whatever the payload expands to
def read_upload(payload: bytes) -> bytes:
    return gzip.decompress(payload)


# CORRECT — inflate at most one byte past the limit, refuse that, and refuse a truncated stream
def read_upload(payload: bytes, *, max_bytes: int = _MAX_DOCUMENT_BYTES) -> bytes:
    inflater = zlib.decompressobj(wbits=_GZIP_WBITS)
    document = inflater.decompress(payload, max_bytes + 1)
    if len(document) > max_bytes:
        raise PayloadTooLargeError(max_bytes)
    if not inflater.eof:
        raise MalformedPayloadError("compressed stream is truncated")
    return document
```

## Decisions That Fail Closed

### A permission check allows what it lists, and an error inside it denies

**Why:** a check that denies a list of roles allows every role added after it; one that allows a
list denies them. Authorization lives in the service, not only at the edge, and the edge declares
authentication once with the public routes as the reviewed exception.

**Example:**
```python
# WRONG — denies the roles it lists, so a role added next year may refund anything
def can_refund(agent: Agent) -> bool:
    return agent.role not in _ROLES_WITHOUT_REFUNDS


# CORRECT — allows the roles it lists; every other role, a new one included, is denied
def can_refund(agent: Agent) -> bool:
    return agent.role in _REFUNDING_ROLES
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
