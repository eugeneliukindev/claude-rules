---
name: python-pyjwt
description: >-
  PyJWT mechanics for verifying and signing JWTs: pinned algorithms, required claims, audience and
  issuer, PyJWKClient caching and timeouts, its errors, the blocking fetch off the loop, a
  round-trip test. Use when code imports jwt, calls jwt.decode or jwt.encode, or builds a
  PyJWKClient. Not for 401 against 403 (python-auth).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# PyJWT

Checked against PyJWT 2.15.1 with `cryptography`, which RS256 needs — the `pyjwt[crypto]` extra. One
module imports `jwt`; its verifier returns the application's own frozen value and raises the
application's own two errors, a rejected token and unreachable signing keys. How the edge answers
each is `python-auth`.

## The Verifier

### The `except` clauses are the classification, and `InvalidTokenError` alone misses three

**Why:** every rejection `jwt.decode` makes subclasses `InvalidTokenError`, but three failures on
the way there do not. An unknown `kid` raises `PyJWKClientError`, a sibling under `PyJWTError` — a
token signed by a retired key, a client's mistake, becomes a 500 (measured: `isinstance(error,
InvalidTokenError)` is `False`). `PyJWKClientConnectionError` subclasses it and means the key set
could not be fetched — the service's failure, so it is caught first. A key set fetched but empty
raises `PyJWKSetError`, neither of the two — `{"keys": []}` escaped in the measured run — and is
answered like an unreachable key set. A claim of the wrong shape is rejected while the claims are
read into the returned value.

**Example:**
```python
# WRONG — an unknown kid and an empty key set escape as 500s
@final
class MemberPassVerifier:
    def __init__(self, *, signing_keys: PyJWKClient, audience: str, issuer: str) -> None:
        self._signing_keys = signing_keys
        self._audience = audience
        self._issuer = issuer

    def verify(self, token: str) -> MemberPass:
        try:
            signing_key = self._signing_keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
            member_pass = _member_pass_from(claims)
        except InvalidTokenError as error:
            raise MemberTokenRejectedError(type(error).__name__) from error
        return member_pass


# CORRECT — the key set's failures are the service's; every other rejection is the client's
@final
class MemberPassVerifier:
    def __init__(self, *, signing_keys: PyJWKClient, audience: str, issuer: str) -> None:
        self._signing_keys = signing_keys
        self._audience = audience
        self._issuer = issuer

    def verify(self, token: str) -> MemberPass:
        try:
            signing_key = self._signing_keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
            member_pass = _member_pass_from(claims)
        except (PyJWKClientConnectionError, PyJWKSetError) as error:
            raise MembershipKeysUnreachableError(self._signing_keys.uri) from error
        except (PyJWKClientError, InvalidTokenError) as error:
            raise MemberTokenRejectedError(type(error).__name__) from error
        return member_pass
```

### The algorithm list is pinned by the verifier, never read from the token

**Why:** the header is written by whoever sent the token; a verifier that believes it lets the
attacker pick `none`, or `HS256` with the issuer's *public* key as the HMAC secret. PyJWT refuses
the classic pairs, but those refusals are a blocklist — CVE-2022-29217 was an SSH-format public key
accepted as an HMAC secret by any application decoding with every algorithm enabled, fixed in
2.4.0; an explicit single algorithm was not exploitable. A key from `PyJWKClient` is a `PyJWK`, and
then PyJWT falls back to the key's own `alg` or a guess from its type — `algorithms` is passed
anyway. One family per key, never `"none"`, never `get_default_algorithms()`.
`get_unverified_header` and `verify_signature: False` decide nothing.

**Example:**
```python
# WRONG — the token chooses how it is checked
def decode_member_token(token: str, signing_key: PyJWK) -> dict[str, object]:
    return jwt.decode(token, signing_key, algorithms=[jwt.get_unverified_header(token)["alg"]])


# CORRECT — the verifier names the one algorithm its issuer signs with
_ALGORITHMS: Final = ("RS256",)


def decode_member_token(token: str, signing_key: PyJWK) -> dict[str, object]:
    return jwt.decode(token, signing_key, algorithms=_ALGORITHMS)
```

### The audience and the issuer are passed, the time claims required, and the leeway is seconds

**Why:** PyJWT checks `iss` only when `issuer` is passed, and `exp`, `iat` and `nbf` only when the
token happens to carry them — measured, a token from another issuer decoded without `issuer=`, and
one without `exp` never expires. A token minted by the same identity provider for another service is
signed by the same key and differs only in its audience. `leeway` absorbs clock skew between two
hosts: thirty seconds covers drift; an hour added to stop a flaky test is an hour of extra life on
every stolen token.

**Example:**
```python
# WRONG — "Invalid audience" silenced, iss never compared, and a token without exp lives forever
def decode_member_claims(token: str, signing_key: PyJWK) -> dict[str, object]:
    return jwt.decode(token, signing_key, algorithms=_ALGORITHMS, options={"verify_aud": False})


# CORRECT — this service's audience, its one issuer, the claims every decision reads made mandatory
def decode_member_claims(
    token: str,
    signing_key: PyJWK,
    *,
    audience: str,
    issuer: str,
    clock_skew_seconds: float = _CLOCK_SKEW_SECONDS,
) -> dict[str, object]:
    return jwt.decode(
        token,
        signing_key,
        algorithms=_ALGORITHMS,
        audience=audience,
        issuer=issuer,
        leeway=clock_skew_seconds,
        options={"require": ["exp", "iat", "sub"]},
    )
```

### `PyJWKClient` is built once by the root, with a timeout, and `verify` is kept off the event loop

**Why:** it caches the key set — `lifespan=300` seconds by default — and refetches on an unknown
`kid` no sooner than `cooldown_duration` (30 s) after its last fetch, so invented `kid`s cannot
flood the issuer; all of it lives on the instance — measured, three clients built per call fetched
three times, one shared client none. Its timeout defaults to 30 s. The fetch is blocking `urllib`,
so `verify` blocks: an async caller runs it through `asyncio.to_thread` or a framework's
thread pool. Keys come from the configured URL, never a `jku` or `x5u` header.

**Example:**
```python
# WRONG — a client per call: the cache dies with it, and every request fetches the key set
def member_signing_key(token: str, *, jwks_url: str) -> PyJWK:
    return PyJWKClient(jwks_url).get_signing_key_from_jwt(token)


# CORRECT — built once by the root and passed in; the cache and the cooldown survive between calls
def build_member_signing_keys(
    jwks_url: str,
    *,
    lifespan_seconds: float = _JWKS_LIFESPAN_SECONDS,
    timeout_seconds: float = _JWKS_TIMEOUT_SECONDS,
) -> PyJWKClient:
    return PyJWKClient(jwks_url, lifespan=lifespan_seconds, timeout=timeout_seconds)
```

## Issuing

**Before signing tokens with `jwt.encode`, read [issuing.md](issuing.md)** — the `kid` header,
aware datetimes from an injected clock.

- A token is signed with its `kid` in the header, and its times come from the injected clock

## Testing

**Before testing the JWT verifier, read [testing.md](testing.md)** — a generated key and a local key
set, the rejections as one parametrized test, the unknown `kid` and the unreachable key set on their
own, forged tokens built by hand.

- The key is generated once, its public half served as a key set the verifier fetches
- PyJWT's rejections are one parametrized test; the unknown `kid` and the outage stand apart
- A forged token is built by hand, because `jwt.encode` refuses to forge one
