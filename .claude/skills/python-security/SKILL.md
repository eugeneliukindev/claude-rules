---
name: python-security
description: >-
  Handles input from outside and who may act on it: parameterized SQL, subprocess arguments, safe
  parsers, paths, uploads, archives, SSRF, size limits, passwords, tokens, permissions. ALWAYS
  invoke this skill when code handles a request body, a filename, an upload, a URL, an Authorization
  header, a cookie or a subprocess argument, or checks a role or an owner. Do not handle such input
  directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Security

Input from outside the process, and who may act on what it asks for, whatever library reads it:
the untrusted data and the decisions that fail closed here, and authentication, authorization,
issued tokens and service credentials in the `auth` files below. The rules name the function,
because the function is what gets copied. Where a secret lives is `python-wiring`; keeping it out of
a `repr` and a `LiteralString` check are `python-types`.

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

- A password is hashed with Argon2id, or scrypt with every parameter stated

## Paths, Uploads and Archives

**Before building a path from outside input, storing an upload, or extracting an archive, read
[paths.md](paths.md)** — resolve then compare components, a generated storage name, the `data`
extraction filter.

- A path from outside input is resolved, then checked component by component against its base
- An upload is stored under a generated name; the user's name is data for display
- A tar archive is extracted with `filter="data"`

## URLs From Outside

**Before fetching a URL a user supplied, read [ssrf.md](ssrf.md)** — an allowlist checked against
the resolved addresses, and every redirect checked before it is followed.

- Every hop is checked on the addresses its name resolves to, and redirects are followed by hand

## Authentication and Authorization

**Before code reads an `Authorization` header or a session cookie, checks a role, a scope or a
permission, or decides who may see a resource, read [auth.md](auth.md)** — a token verified into a
frozen caller, the check in the service beside the load, 401 against 403, the session cookie.

- The application verifies tokens through one contract that returns a frozen caller, and a service takes that caller, never the token or the claims
- Nothing in a token is believed before its signature, and its claims model ignores extra claims
- Whether this caller may touch this resource is checked in the service — next to the load for one, in the query for a list
- A caller who may see a resource but not act on it gets a permission error
- No valid credentials is 401, a valid caller refused is 403, unreachable signing keys are 503
- A token travels in a header, and the access log records an allowlist of headers
- A session cookie is `Secure`, `HttpOnly`, `SameSite` and `__Host-`-prefixed

## Issuing Tokens and Guarding Credentials

**Before issuing access or refresh tokens, rotating signing keys, or writing a sign-in,
password-reset or token endpoint, read [auth-issuing.md](auth-issuing.md)** — short access tokens,
rotated refresh tokens, key rotation through the key set, shared attempt limits per account and per
source.

- An access token lives minutes, and carries `iss`, `aud`, `sub`, `iat`, `exp`, `jti` and `kid`
- A refresh token is opaque, stored hashed, and rotated on every use
- A signing key rotates through the key set: publish, wait the cache lifetime, sign, retire
- A credential endpoint counts attempts per account and per source, in the shared cache

## Service-to-Service Credentials

**Before one service calls another with a credential, read
[auth-service-credentials.md](auth-service-credentials.md)** — a credential per service, the
audience named, no forwarded user tokens across a boundary, an outbound token fetched once and
reused.

- Each service has its own credential, and the token names the service it is for
- An outbound token is fetched once and reused until shortly before its `exp`

## Testing

**Before testing authentication or authorization, read [auth-testing.md](auth-testing.md)** — a
fake verifier, one contract suite with a harness per implementation, authorization tested at the
service with the owner and another pupil.

- A fake verifier issues opaque tokens and can lose its signing keys, and every implementation hands the one contract suite a harness that does both
- Authorization is tested at the service, with the owner and another pupil
