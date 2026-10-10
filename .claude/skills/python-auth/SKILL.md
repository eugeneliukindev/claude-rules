---
name: python-auth
description: >-
  Authentication and authorization design in Python services, whatever the token library: a
  TokenVerifier contract that turns a bearer token into a typed principal at the edge or raises a
  classified error, an invalid token answered 401 without saying which check failed and an
  unreachable key set 503, object-level authorization in the service against IDOR, 401 versus 403,
  tokens kept out of logs, session cookie flags, token lifetime and refresh rotation,
  service-to-service credentials, and testing with a fake verifier. Use when Python code verifies
  a bearer token or an Authorization header, sets a session cookie, or checks a permission, a role,
  a scope or who owns a resource; PyJWT's own mechanics are in python-pyjwt.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Authentication and Authorization

Checked against FastAPI 0.143 and Starlette 1.7 at the edge. `python-security` owns the primitives
this file builds on — `secrets` for anything capability-bearing, Argon2 for passwords,
`hmac.compare_digest` for secrets, failing closed and denying by default — and `python-fastapi`
owns where authentication is declared: once, on the protected router. What follows is what sits
between them: how a token becomes an identity, and where that identity is checked. How one token
library verifies a token is that library's skill — PyJWT's is `python-pyjwt`.

## A Token Becomes a Principal Behind a Contract

The application never sees a token library. It sees one contract, named for the capability
(`python-contracts`): `TokenVerifier.verify(token)` returns who the token speaks for, or raises one
of two classified errors. The composition root picks the implementation — `JwtTokenVerifier` over
PyJWT, an introspection client — and the unit tests take a fake.

```
authentication/
    base.py        # TokenVerifier(ABC), AuthenticationError and its two leaves
    pyjwt.py       # JwtTokenVerifier(TokenVerifier) — the only file that imports jwt
    __init__.py    # the contract, the errors and the implementations, nothing else
tests/fakes.py     # InMemoryTokenVerifier(TokenVerifier)
```

```python
UserId = NewType("UserId", str)


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Principal:
    user_id: UserId
    scopes: frozenset[str]


class AuthenticationError(Exception):
    """Root of the authentication package's errors."""


class InvalidCredentialsError(AuthenticationError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Credentials rejected: {reason}")
        self.reason = reason


class KeySetUnavailableError(AuthenticationError):
    def __init__(self, key_set_url: str) -> None:
        super().__init__(f"Key set {key_set_url} could not be fetched")
        self.key_set_url = key_set_url


class TokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str) -> Principal:
        """Return who the token speaks for, or raise one of this module's errors."""
```

- **Two failures, two errors, and nothing else escapes.** `InvalidCredentialsError` means the
  token must not be accepted — malformed, forged, expired, for another audience, signed by a key
  nobody publishes: the client's mistake. `KeySetUnavailableError` means the keys to check it
  cannot be had right now: the service's failure. Every library exception is translated inside the
  implementation; one that escapes is a 500 for what was a client's expired token, and PyJWT has
  two that slip past the obvious `except` (`python-pyjwt`). Both errors fail closed — no request
  passes without a verified token.
- **Verified claims become a `Principal` inside the implementation; the token stops at the edge.**
  The decoded claims are a boundary payload like any other, validated into a model and returned as
  a frozen domain object (`python-boundaries`). One carve-out from strict boundary models: **the
  claims model ignores extra claims** rather than forbidding them, because the claim set is the
  identity provider's contract, not yours, and it adds claims without telling you.
- **Nothing in a token is believed before its signature is.** Not the algorithm its header names,
  not a key URL in it (`jku`, `x5u`), not its `sub`. A JWT implementation pins its algorithms and
  requires the audience, the issuer and an expiry, whatever the library; PyJWT's spelling of each
  is `python-pyjwt`.
- **The services take the `Principal`, never the token or the claims.** A service handed the token
  decodes it again with its own idea of the algorithms; one handed the claims trusts whatever dict
  it was given, from a test or a queue message alike.

```python
# WRONG — the service receives the credential, and every caller must have a token to call it
async def get_order(self, token: str, order_id: OrderId) -> Order: ...

# CORRECT — the service receives who is asking; a worker or a test builds a Principal directly
async def get_order(self, principal: Principal, order_id: OrderId) -> Order: ...
```

## Authentication Is Not Authorization

The router establishes **who** is calling; it cannot know **whether this caller may touch this
resource**, because it has not loaded the resource. That check is object-level and lives in the
service, next to the load. An `/orders/{order_id}` route guarded by "is logged in" or by a role
lets every user read every order whose id they can guess or enumerate — the most common access
control flaw there is (IDOR). Opaque ids (`python-boundaries`) make guessing harder; they do not
make the check optional.

```python
# WRONG — any authenticated caller who knows an id gets the order
async def get_order(self, principal: Principal, order_id: OrderId) -> Order:
    order = await self._repository.find(order_id)
    if order is None:
        raise OrderNotFoundError(order_id)
    return order

# CORRECT — someone else's order is answered exactly like a missing one
async def get_order(self, principal: Principal, order_id: OrderId) -> Order:
    order = await self._repository.find(order_id)
    if order is None or not _can_read(principal, order):
        raise OrderNotFoundError(order_id)
    return order


def _can_read(principal: Principal, order: Order) -> bool:
    return order.owner_id == principal.user_id or _READ_ANY_ORDER_SCOPE in principal.scopes
```

- **Not found or forbidden is chosen per resource.** Where the existence of the resource is itself
  the secret — another user's order — the denial is indistinguishable from absence, or a 403
  confirms the id is real. Where the caller may see the resource but not perform the action — read
  an order, not refund it — the service raises a permission error the handler maps to 403.
- **A list is authorized by its query, not by filtering the result.** The repository takes the
  owner — `find_for_owner(principal.user_id, ...)` — so pagination, counts and totals never see
  rows the caller may not.
- **A scope or a role is a coarse gate; ownership is the fine one.** The router may require
  `orders:read` before the service runs; the service still checks which orders. In GraphQL that
  gate is a permission class on the field (`python-strawberry`).

## 401 or 403, and Nothing About Which Check Failed

- **401 means no valid credentials** — missing, malformed, expired, wrong audience, unknown key —
  and carries `WWW-Authenticate: Bearer`, which tells a client to authenticate again. **403 means
  the credentials are valid and this caller may not do this.** FastAPI's `HTTPBearer` already
  answers a missing header with a 401 and that header; the verifier's failures must match it.
- **Every rejected token gets the same body.** "Signature has expired" versus "Invalid audience"
  tells someone probing with a stolen or forged token which checks they have already passed. The
  reason goes to the server's records — `InvalidCredentialsError.reason` and the chained cause, and
  a counter with a `reason` attribute shows a wave of rejections (`python-observability`). Logged
  at `INFO` at most: a rejected token is an expected client mistake (`logging.md`).
- **A key set that cannot be fetched is a 503, not a 401.** Answered as a 401, every client drops
  its session and re-authenticates against an outage, and the alert says "users failing login".

The root builds the verifier and the lifespan yields it as `token_verifier`; `BearerCredentials` is
`Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())]`. The dependency is a plain `def`:
`verify` may block on a key set fetch, so it runs in FastAPI's thread pool (why: `python-pyjwt`).

```python
# WRONG — the body names the failed check: "InvalidAudienceError" says the signature was good
def require_principal(request: Request, credentials: BearerCredentials) -> Principal:
    token_verifier: TokenVerifier = request.state.token_verifier
    try:
        return token_verifier.verify(credentials.credentials)
    except InvalidCredentialsError as error:
        raise HTTPException(
            HTTPStatus.UNAUTHORIZED, error.reason, headers={"WWW-Authenticate": "Bearer"}
        ) from error
    except KeySetUnavailableError as error:
        raise HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, "Try again later") from error

# CORRECT — one fixed body for every rejected token; the reason stays on the chained cause
def require_principal(request: Request, credentials: BearerCredentials) -> Principal:
    token_verifier: TokenVerifier = request.state.token_verifier
    try:
        return token_verifier.verify(credentials.credentials)
    except InvalidCredentialsError as error:
        raise HTTPException(
            HTTPStatus.UNAUTHORIZED, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"}
        ) from error
    except KeySetUnavailableError as error:
        raise HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, "Try again later") from error
```

`HTTPException` is right here, not the domain error handler: authentication failing is a failure
that exists only in HTTP, raised by the transport layer (`python-fastapi`).

## Tokens Stay Out of Logs

A bearer token is a password with an expiry: whoever reads it from a log replays it until then.
`logging.md` and `python-security` forbid logging secrets; for authentication that means, in
particular:

- **No `Authorization` or `Cookie` header in any log line** — the access-log middleware that
  logs "all headers" is the usual leak; it logs an allowlist of headers, never a denylist.
- **No token in an exception message, a span attribute or a URL.** Tokens travel in the header,
  never in the query string, which lands in proxy logs and browser history. The contract's errors
  above carry the reason and the key set URL, never the token.
- **Log the principal's id, not the claims.** Claims carry e-mail addresses and names.

## Session Cookies

Where the client is a browser, the session is usually a cookie holding an opaque id from
`secrets.token_urlsafe` (`python-security`), not a JWT. Starlette's `set_cookie` defaults to
`secure=False` and `httponly=False`; every flag is set on purpose.

```python
# WRONG — the defaults: readable by any script on the page, and sent over plain HTTP
response.set_cookie(_SESSION_COOKIE, session_id, max_age=_SESSION_MAX_AGE_SECONDS)

# CORRECT — HTTPS only, invisible to JavaScript, withheld from cross-site subrequests
response.set_cookie(
    _SESSION_COOKIE,
    session_id,
    max_age=_SESSION_MAX_AGE_SECONDS,
    secure=True,
    httponly=True,
    samesite="lax",
)
```

A `__Host-` name prefix (`_SESSION_COOKIE: Final = "__Host-session"`) makes the browser refuse the
cookie unless it is `Secure`, has `Path=/` and no `Domain` — Starlette's defaults for the last two.
`SameSite` narrows cross-site requests; it does not replace CSRF protection for state-changing
requests authenticated by a cookie.

## Issuing Tokens

Prefer an identity provider; this file is about verifying. Where a service issues its own:

- **Access tokens live minutes, not days**, because a JWT cannot be revoked before its `exp`. Every
  token carries `iss`, `aud`, `sub`, `iat`, `exp` and a `jti` from `secrets`, and a `kid` header
  naming the key that signed it. The clock is injected (`functions.md`).
- **Refresh tokens are opaque, stored hashed, and rotated on every use.** A refresh token presented
  a second time means it was copied: revoke the whole family it belongs to, not just that token.
- **Signing keys rotate through the key set**: publish the new public key, wait at least the
  verifiers' cache lifetime, then sign with it; remove the old key once its last token has expired.

## Service-to-Service Credentials

- **Each service has its own credential** — a client-credentials token from the identity provider,
  a workload identity, or mutual TLS — never one static key shared by every caller, which cannot
  be rotated without a coordinated deploy or revoked for one caller alone.
- **The token names the service it is for in `aud`**, and the receiving service verifies it like
  any other. A token minted for one service and replayed against another is then rejected.
- **A user's token is not forwarded to a third party.** Inside one trust domain the next service
  may verify the same token with its own audience in the list, or exchange it for one of its own;
  across a boundary the call uses the service's own credential.
- **The outbound token is fetched once and reused until shortly before its `exp`**, by the client
  object the root owns — not fetched per request, and its secret comes from the environment or a
  secret manager (`python-security`). Over gRPC it travels as per-call credentials, which need a
  secure channel (`python-grpc`).

## Testing

**The unit tests take a fake verifier.** It issues opaque tokens, maps them back to the principals
it issued them for, and stops answering when its key set is taken offline:

```python
@final
class InMemoryTokenVerifier(TokenVerifier):
    def __init__(self) -> None:
        self._principal_by_token: dict[str, Principal] = {}
        self.is_key_set_reachable = True

    def issue(self, principal: Principal) -> str:
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        self._principal_by_token[token] = principal
        return token

    @override
    def verify(self, token: str) -> Principal:
        if not self.is_key_set_reachable:
            raise KeySetUnavailableError(_KEY_SET_URL)
        principal = self._principal_by_token.get(token)
        if principal is None:
            raise InvalidCredentialsError("unknown token")
        return principal
```

**The fake and every real implementation pass one contract suite** (`python-contracts`). Issuing a
token and taking the key set offline differ per implementation, so each implementation's fixture
hands the tests a harness with both; the JWT one, with a generated key and a local key set server,
is in `python-pyjwt`.

```python
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class TokenVerifierHarness:
    verifier: TokenVerifier
    issue_token: Callable[[Principal], str]
    take_key_set_offline: Callable[[], None]


@pytest.fixture
def memory_token_verifier_harness() -> TokenVerifierHarness:
    verifier = InMemoryTokenVerifier()

    def take_key_set_offline() -> None:
        verifier.is_key_set_reachable = False

    return TokenVerifierHarness(
        verifier=verifier, issue_token=verifier.issue, take_key_set_offline=take_key_set_offline
    )


@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("jwt", id="jwt", marks=pytest.mark.integration),
    ]
)
def token_verifier_harness(request: pytest.FixtureRequest) -> TokenVerifierHarness:
    harness: TokenVerifierHarness = request.getfixturevalue(
        f"{request.param}_token_verifier_harness"
    )
    return harness


def test_verify_returns_principal_the_token_was_issued_to(
    token_verifier_harness: TokenVerifierHarness,
) -> None:
    principal = make_principal(scopes=frozenset({"orders:read"}))
    token = token_verifier_harness.issue_token(principal)

    verified = token_verifier_harness.verifier.verify(token)

    assert verified == principal


def test_verify_reports_unreachable_key_set_as_unavailable(
    token_verifier_harness: TokenVerifierHarness,
) -> None:
    token = token_verifier_harness.issue_token(make_principal())
    token_verifier_harness.take_key_set_offline()

    with pytest.raises(KeySetUnavailableError, match="could not be fetched"):
        token_verifier_harness.verifier.verify(token)
```

- **A third contract test sends a token nobody issued** and expects `InvalidCredentialsError`. The
  rejections only one implementation can produce — an expired JWT, a wrong audience, `alg` `none`
  — are that implementation's own tests (`python-pyjwt`).
- **Routes are tested through the app built with the fake**: a token from `issue` gets through,
  `"Bearer forged"` gets the fixed 401 body with `WWW-Authenticate`, and `is_key_set_reachable =
  False` gets the 503 — the edge's mapping is then under test too, which a principal overridden
  with `dependency_overrides` skips (`python-fastapi`).
- **The authorization tests live at the service**, with a principal that owns the resource and one
  that does not — the second is the test that catches IDOR.
