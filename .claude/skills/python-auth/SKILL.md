---
name: python-auth
description: >-
  Designs authentication and authorization whatever the token library: a bearer token verified
  into a principal, 401 against 403, object-level checks, session cookies, token lifetime, service
  credentials. Use when code reads an Authorization header or a session cookie, checks a role,
  scope or permission, or decides who may see a resource.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Authentication and Authorization

How a token becomes an identity, and where that identity is checked, whatever the token library.
The primitives — `secrets` for capability-bearing values, Argon2, `hmac.compare_digest`, failing
closed — are `python-security`. A JWT verified with PyJWT is `python-pyjwt`; the FastAPI dependency
that calls the verifier and sets a cookie is `python-fastapi`; a GraphQL permission class is
`python-strawberry`; per-call credentials on a gRPC channel are `python-grpc`.

## A Token Becomes a Principal

### The application verifies tokens through a `TokenVerifier` contract that returns a `Principal`

**Why:** the application never sees a token library. `TokenVerifier.verify(token)` returns who the
token speaks for, or raises one of two errors: `InvalidCredentialsError` — malformed, forged,
expired, another audience, an unknown key: the client's mistake — or `KeySetUnavailableError` —
the keys cannot be had right now: the service's failure. Every library exception is translated
inside the implementation, and both fail closed. The contract lives in `authentication/base.py`,
each implementation beside it is the only file importing its library, and the unit tests take a
fake (`python-contracts`).

**Example:**
```python
# WRONG — the service decodes the token itself, with its own idea of the algorithms and errors
@final
class DocumentAccess:
    def __init__(self, *, signing_key: str, documents: DocumentStore) -> None:
        self._signing_key = signing_key
        self._documents = documents

    async def open(self, token: str, document_id: DocumentId) -> Document:
        claims = jwt.decode(token, self._signing_key, algorithms=["HS256"])
        return await self._documents.get_for_owner(document_id, owner_id=UserId(claims["sub"]))


# CORRECT — one contract, a frozen principal, two classified errors
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Principal:
    user_id: UserId
    scopes: frozenset[str]


class AuthenticationError(Exception):
    """Root of the authentication package's errors."""


class InvalidCredentialsError(AuthenticationError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"credentials rejected: {reason}")
        self.reason = reason


class KeySetUnavailableError(AuthenticationError):
    def __init__(self, key_set_url: str) -> None:
        super().__init__(f"key set {key_set_url} could not be fetched")
        self.key_set_url = key_set_url


class TokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str) -> Principal:
        """Return who the token speaks for, or raise one of this module's errors."""
```

### Nothing in a token is believed before its signature, and its claims model ignores extra claims

**Why:** not the algorithm its header names, not a key URL in it (`jku`, `x5u`), not its `sub`; a
JWT implementation pins its algorithms and requires the audience, the issuer and an expiry. The
decoded claims are a boundary payload validated into a model (`python-boundaries`), with one
carve-out from strict models: the claim set is the identity provider's contract, which adds claims
without telling you, so extra claims are ignored rather than refused.

**Example:**
```python
# WRONG — the provider adds a "sid" claim one morning, and every token is rejected
class AccessClaims(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    sub: str
    scope: str = ""


# CORRECT — the claims this service reads are validated; the provider's additions pass by
class AccessClaims(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    sub: str
    scope: str = ""
```

### A service takes the `Principal`, never the token or the claims

**Why:** a service handed the token decodes it again with its own idea of the algorithms; one handed
the claims trusts whatever dict it was given, from a test or a queue message alike. With a
`Principal`, a worker or a test builds the caller directly.

**Example:**
```python
# WRONG — every caller must hold a token to call the service
@final
class DocumentAccess:
    def __init__(self, *, documents: DocumentStore) -> None:
        self._documents = documents

    async def open(self, token: str, document_id: DocumentId) -> Document:
        return await self._documents.get(document_id)


# CORRECT — the service receives who is asking
@final
class DocumentAccess:
    def __init__(self, *, documents: DocumentStore) -> None:
        self._documents = documents

    async def open(self, principal: Principal, document_id: DocumentId) -> Document:
        return await _readable(principal, await self._documents.find(document_id), document_id)
```

## Authorization

### Whether this caller may touch this resource is checked in the service, next to the load

**Why:** the edge establishes who is calling; it has not loaded the resource, so it cannot know
whether the caller may touch it. A route guarded by "is logged in" or by a role lets every user read
every document whose id they can guess or enumerate — IDOR, the most common access-control flaw.
Opaque ids make guessing harder; they do not make the check optional. Where the resource's
existence is itself the secret, someone else's document is answered exactly like a missing one; a
403 would confirm the id is real.

**Example:**
```python
# WRONG — any authenticated caller who knows an id gets the document
async def _readable(
    principal: Principal, document: Document | None, document_id: DocumentId
) -> Document:
    if document is None:
        raise DocumentNotFoundError(document_id)
    return document


# CORRECT — someone else's document is answered exactly like a missing one
async def _readable(
    principal: Principal, document: Document | None, document_id: DocumentId
) -> Document:
    if document is None or not _can_read(principal, document):
        raise DocumentNotFoundError(document_id)
    return document


def _can_read(principal: Principal, document: Document) -> bool:
    return document.owner_id == principal.user_id or _READ_ANY_DOCUMENT_SCOPE in principal.scopes
```

### A caller who may see a resource but not act on it gets a permission error

**Why:** not found or forbidden is chosen per resource. Where the caller may read a document but
not delete it, its existence is no secret, and the service raises a permission error the edge maps
to 403. A scope or a role is the coarse gate the edge may check first; ownership is the fine one
the service always checks.

**Example:**
```python
# WRONG — anyone who can read the document can delete it
@final
class DocumentAccess:
    def __init__(self, *, documents: DocumentStore) -> None:
        self._documents = documents

    async def delete(self, principal: Principal, document_id: DocumentId) -> None:
        document = await _readable(principal, await self._documents.find(document_id), document_id)
        await self._documents.delete(document.document_id)


# CORRECT — reading and deleting are different permissions
@final
class DocumentAccess:
    def __init__(self, *, documents: DocumentStore) -> None:
        self._documents = documents

    async def delete(self, principal: Principal, document_id: DocumentId) -> None:
        document = await _readable(principal, await self._documents.find(document_id), document_id)
        if document.owner_id != principal.user_id:
            raise DocumentPermissionError(document_id, action="delete")
        await self._documents.delete(document.document_id)
```

### A list is authorized by its query, never by filtering the result

**Why:** filtering after the query lets pagination, counts and totals see rows the caller may not —
page one holds three documents of fifty, and the total gives away the rest. The repository takes the
owner.

**Example:**
```python
# WRONG — the page and its total are computed over everyone's documents
@final
class DocumentAccess:
    def __init__(self, *, documents: DocumentStore) -> None:
        self._documents = documents

    async def list_documents(self, principal: Principal, *, page: PageRequest) -> DocumentPage:
        documents = await self._documents.page(page)
        visible = [document for document in documents.items if _can_read(principal, document)]
        return DocumentPage(items=visible, total=documents.total)


# CORRECT — the query itself is scoped to the caller
@final
class DocumentAccess:
    def __init__(self, *, documents: DocumentStore) -> None:
        self._documents = documents

    async def list_documents(self, principal: Principal, *, page: PageRequest) -> DocumentPage:
        return await self._documents.page_for_owner(principal.user_id, page)
```

## Rejections

### No valid credentials is 401, a valid caller refused is 403, an unreachable key set is 503

**Why:** 401 carries `WWW-Authenticate: Bearer` and tells a client to authenticate again; 403 says
the credentials are fine and the action is not. A key set that cannot be fetched answered as 401
makes every client drop its session against an outage, and the alert says "users failing login".
Every rejected token gets the same body: "Signature has expired" against "Invalid audience" tells
someone probing with a stolen token which checks passed. The reason goes to the server's records —
the chained cause, and a counter with a `reason` attribute (`python-observability`) — at `INFO` at
most, since a rejected token is an expected client mistake.

**Example:**
```python
# WRONG — the reason reaches the client, and an outage looks like bad credentials
def rejection_for(error: AuthenticationError) -> Rejection:
    return Rejection(status=HTTPStatus.UNAUTHORIZED, body=str(error))


# CORRECT — one fixed body per kind of failure; the reason stays on the server
def rejection_for(error: AuthenticationError) -> Rejection:
    match error:
        case KeySetUnavailableError():
            return Rejection(status=HTTPStatus.SERVICE_UNAVAILABLE, body="Try again later")
        case _:
            return Rejection(
                status=HTTPStatus.UNAUTHORIZED,
                body="Invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
```

### Tokens and cookies never reach a log, a span or a URL

**Why:** a bearer token is a password with an expiry — whoever reads it from a log replays it until
then. The access log records an allowlist of headers, never a denylist with `Authorization` and
`Cookie` struck out; a token travels in a header, never the query string, which lands in proxy logs
and browser history; the principal's id is logged, never the claims, which carry e-mail addresses
and names.

**Example:**
```python
# WRONG — "all headers but a few": Authorization arrives under a new spelling and is logged
def loggable_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {name: value for name, value in headers.items() if name.lower() != "authorization"}


# CORRECT — only the headers named as safe are ever logged
_LOGGED_HEADERS: Final = frozenset({"user-agent", "x-request-id", "content-type"})


def loggable_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {name: value for name, value in headers.items() if name.lower() in _LOGGED_HEADERS}
```

### A session cookie is `Secure`, `HttpOnly`, `SameSite` and `__Host-`-prefixed

**Why:** a browser session is an opaque id from `secrets.token_urlsafe`, not a JWT. Without
`Secure` it travels over plain HTTP; without `HttpOnly` any script on the page reads it; `SameSite`
withholds it from cross-site subrequests, though it does not replace CSRF protection for
state-changing requests. The `__Host-` prefix makes the browser refuse the cookie unless it is
`Secure`, has `Path=/` and no `Domain`. Frameworks default to none of this.

**Example:**
```python
# WRONG — readable by any script on the page, and sent over plain HTTP
def session_cookie_header(session_id: str, *, max_age_seconds: int) -> str:
    return f"session={session_id}; Max-Age={max_age_seconds}; Path=/"


# CORRECT — HTTPS only, invisible to JavaScript, withheld from cross-site subrequests
def session_cookie_header(session_id: str, *, max_age_seconds: int) -> str:
    return (
        f"__Host-session={session_id}; Max-Age={max_age_seconds}; Path=/; "
        "Secure; HttpOnly; SameSite=Lax"
    )
```

## Issuing Tokens and Guarding Credentials

**Before issuing access or refresh tokens, rotating signing keys, or writing a login, password-reset
or token endpoint, read [issuing.md](issuing.md)** — short access tokens, rotated refresh tokens,
key rotation through the key set, shared rate limits per account and per source.

## Service-to-Service Credentials

**Before one service calls another with a credential, read
[service-credentials.md](service-credentials.md)** — a credential per service, the audience named,
no forwarded user tokens across a boundary, an outbound token fetched once and reused.

## Testing

**Before testing authentication or authorization, read [testing.md](testing.md)** — a fake verifier,
one contract suite with a harness per implementation, authorization tested at the service with an
owner and a stranger.
