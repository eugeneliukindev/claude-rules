---
name: python-pyjwt
description: >-
  PyJWT mechanics behind the TokenVerifier contract, the design being in python-auth:
  JwtTokenVerifier with the algorithm list pinned on jwt.decode rather than read from the token
  header, audience and issuer passed and exp, iat and sub required, a leeway of seconds, PyJWKClient
  built once by the root with its cache, refetch cooldown and timeout, PyJWKClientError and
  PyJWKSetError caught beside InvalidTokenError, the blocking key set fetch kept off the event loop,
  CVE-2022-29217, and the round-trip test against a generated RSA key and a local JWKS server. Use
  when Python code imports jwt, calls jwt.decode or jwt.encode, or builds a PyJWKClient.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# PyJWT

Checked against PyJWT 2.15.1 with `cryptography`, which RS256 needs — the `pyjwt[crypto]` extra.
The contract this implements, the `Principal` it returns, its two errors and how the edge answers
them are `python-auth`; what follows is the implementation and the library's own traps.

## The Implementation

`authentication/pyjwt.py`, the only module that imports `jwt` (`python-contracts`):

```python
_ALGORITHMS: Final = ("RS256",)
_CLOCK_SKEW: Final = timedelta(seconds=30)
_JWKS_LIFESPAN_SECONDS: Final = 300
_JWKS_TIMEOUT_SECONDS: Final = 2.0


@final
class _AccessTokenClaims(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    sub: str
    scope: str = ""

    def to_principal(self) -> Principal:
        return Principal(user_id=UserId(self.sub), scopes=frozenset(self.scope.split()))


@final
class JwtTokenVerifier(TokenVerifier):
    def __init__(self, signing_keys: PyJWKClient, *, audience: str, issuer: str) -> None:
        self._signing_keys = signing_keys
        self._audience = audience
        self._issuer = issuer

    @override
    def verify(self, token: str) -> Principal:
        try:
            signing_key = self._signing_keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                leeway=_CLOCK_SKEW,
                options={"require": ["exp", "iat", "sub"]},
            )
            access_claims = _AccessTokenClaims.model_validate(claims)
        except (PyJWKClientConnectionError, PyJWKSetError) as error:
            raise KeySetUnavailableError(self._signing_keys.uri) from error
        except (PyJWKClientError, InvalidTokenError, ValidationError) as error:
            raise InvalidCredentialsError(type(error).__name__) from error
        return access_claims.to_principal()


def build_signing_keys(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, lifespan=_JWKS_LIFESPAN_SECONDS, timeout=_JWKS_TIMEOUT_SECONDS)
```

**The `except` clauses are the classification, and `InvalidTokenError` alone is not enough.**
Every rejection `jwt.decode` makes is a subclass of it; two failures on the way there are not:

- **An unknown `kid` raises `PyJWKClientError`**, a sibling of `InvalidTokenError` under
  `PyJWTError`. An `except InvalidTokenError` lets it through, and a token signed by a retired key
  — a client's mistake — becomes a 500. Measured: `isinstance(error, InvalidTokenError)` is `False`.
- **`PyJWKClientConnectionError` subclasses `PyJWKClientError`** and means the key set could not be
  fetched — a refused connection, a timeout, a 503 from the issuer. It is the service's failure, so
  it is caught first and becomes `KeySetUnavailableError`.
- **A key set fetched but empty or unusable raises `PyJWKSetError`**, which is neither of the two:
  `{"keys": []}` escaped `except (PyJWKClientError, InvalidTokenError)` in the measured run. It is
  the issuer's failure, answered like an unreachable key set.
- **A claim of the wrong shape is a `ValidationError`** — a `scope` sent as a list — and a signed
  token whose claims this service cannot read is still not accepted.

## The Algorithm List Is Pinned, Never Read From the Token

A JWT's header names the algorithm it was signed with, and the header is written by whoever sent
the token: a verifier that believes it lets the attacker pick `none`, or `HS256` with the issuer's
*public* key as the HMAC secret. PyJWT refuses the classic pairs — a PEM key as an HMAC secret,
`none` with a key — but those refusals are a blocklist, and a blocklist has gaps:
CVE-2022-29217 (GHSA-ffqj-6fqr-9h24) was an SSH-format Ed25519 or ECDSA public key accepted as an
HMAC secret by any application decoding with every algorithm enabled, fixed in 2.4.0. An explicit
single algorithm was not exploitable.

```python
# WRONG — the token chooses how it is checked: its header names the algorithm the verifier uses
claims = jwt.decode(token, signing_key, algorithms=[jwt.get_unverified_header(token)["alg"]])

# CORRECT — the verifier names the one algorithm its issuer signs with
claims = jwt.decode(token, signing_key, algorithms=_ALGORITHMS)
```

- **`decode` refuses to run without `algorithms` — unless the key is a `PyJWK`.** A key from
  `PyJWKClient` is one, and then PyJWT falls back to the key's own `alg`, and to a guess from its
  key type when the key set names none: an RSA key without `alg` became `RS256` in the measured
  run. Pass `algorithms` anyway — the key set is the issuer's document, the list is your decision.
- **One family per key.** Never `("RS256", "HS256")` for one issuer: a list mixing symmetric and
  asymmetric algorithms is the confusion the pin exists to prevent. Never `"none"` in any list, and
  never `get_default_algorithms()` as the list.
- **`get_unverified_header` and `options={"verify_signature": False}` decide nothing.** They are
  for reading the `kid` that selects the key — which `PyJWKClient` already does — and for
  inspecting a token by hand. A `sub` read that way is whatever the sender typed.

## Audience, Issuer and the Time Claims Are Required

PyJWT checks `iss` only when `issuer` is passed, and checks `exp`, `iat` and `nbf` only when the
token happens to carry them — the documentation's own warning, and the measured behaviour: a token
from another issuer decoded without `issuer=`, and one without `exp` decoded and never expires. A
token minted by the same identity provider for another service is signed by the same key and
differs only in its audience; without the audience check it opens this service too.

```python
# WRONG — "Invalid audience" silenced, iss never compared, and a token without exp lives forever
claims = jwt.decode(token, signing_key, algorithms=_ALGORITHMS, options={"verify_aud": False})

# CORRECT — this service's audience, its one issuer, the claims every decision reads made mandatory
claims = jwt.decode(
    token,
    signing_key,
    algorithms=_ALGORITHMS,
    audience=audience,
    issuer=issuer,
    leeway=_CLOCK_SKEW,
    options={"require": ["exp", "iat", "sub"]},
)
```

**`leeway` absorbs clock skew between two hosts — seconds, not minutes.** `timedelta(seconds=30)`
covers drifting clocks; a leeway of an hour added to stop a flaky test is an hour of extra life on
every stolen token. A host whose clock is minutes off is a broken host, fixed with NTP.

## `PyJWKClient` Is Built Once, With a Timeout

`PyJWKClient` caches the key set — `lifespan=300` seconds by default — and on an unknown `kid`
refetches once, no sooner than `cooldown_duration` (30 s) after its last successful fetch, so a
flood of invented `kid`s cannot turn into a flood of fetches. All of it lives on the instance:
measured, three clients built per call fetched three times, and one shared client fetched none. It
is built once by the composition root with its timeout stated — the default is 30 s — and handed to
the verifier (`python-wiring`). It holds no connection, so there is nothing to close.

```python
# WRONG — a client per call: the cache dies with it, and every request fetches the key set
@override
def verify(self, token: str) -> Principal:
    signing_key = PyJWKClient(self._jwks_url).get_signing_key_from_jwt(token)
    ...

# CORRECT — built once by the root and passed in; the cache and the cooldown survive between calls
def build_signing_keys(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, lifespan=_JWKS_LIFESPAN_SECONDS, timeout=_JWKS_TIMEOUT_SECONDS)
```

- **The fetch is blocking `urllib`, so `verify` blocks.** In FastAPI it is called from a plain
  `def` dependency, which runs in the thread pool; elsewhere in async code through
  `asyncio.to_thread` — never directly inside `async def`, where a slow key set endpoint stops the
  event loop (`python-async`). This is the carve-out from `python-fastapi`'s "an accessor is
  `async def`": a verifier is not an accessor.
- **A token signed with a new `kid` is rejected for up to the cooldown after the last fetch** —
  harmless when the issuer publishes the new key before signing with it, as rotation asks
  (`python-auth`).
- **Keys come from the configured URL, never from a `jku` or `x5u` header in the token.**

## Issuing

`jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": key_id})`. `iat` and `exp` may
be aware `datetime`s, which PyJWT writes as integer seconds; the `now` they are computed from is
injected (`functions.md`). An access token lives minutes, not days, and carries `iss`, `aud`, `sub`,
`iat`, `exp` and a `jti` from `secrets` (why and how: `python-auth`).

## Testing

**The contract suite's JWT harness** (`python-auth`) generates a key pair once per session, serves
its public half as a key set from `pytest-httpserver` (`python-pytest`), issues tokens with
`jwt.encode`, and takes the key set offline by answering 503:

```python
@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks_url(httpserver: HTTPServer, signing_key: rsa.RSAPrivateKey) -> str:
    public_jwk = RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    key_set = {"keys": [public_jwk | {"kid": KEY_ID, "use": "sig", "alg": "RS256"}]}
    httpserver.expect_request(_JWKS_PATH).respond_with_data(
        json.dumps(key_set), content_type="application/json"
    )
    return httpserver.url_for(_JWKS_PATH)


@pytest.fixture
def jwt_token_verifier_harness(
    httpserver: HTTPServer, signing_key: rsa.RSAPrivateKey, jwks_url: str
) -> TokenVerifierHarness:
    verifier = JwtTokenVerifier(build_signing_keys(jwks_url), audience=AUDIENCE, issuer=ISSUER)

    def issue_token(principal: Principal) -> str:
        return issue_jwt(signing_key, principal)

    def take_key_set_offline() -> None:
        httpserver.clear_all_handlers()
        httpserver.expect_request(_JWKS_PATH).respond_with_data("", status=503)

    return TokenVerifierHarness(
        verifier=verifier, issue_token=issue_token, take_key_set_offline=take_key_set_offline
    )
```

**PyJWT's own rejections are one parametrized test**, each case asserting
`InvalidCredentialsError` — and the unknown `kid` a test of its own, because it is the one an
`except InvalidTokenError` lets through:

```python
@pytest.mark.parametrize(
    "claims",
    [
        pytest.param(
            make_claims(exp=int(time.time()) - _PAST_LEEWAY_SECONDS), id="expired_past_leeway"
        ),
        pytest.param(make_claims(aud="https://billing.example.com"), id="other_audience"),
        pytest.param(make_claims(iss="https://other-issuer.example.com/"), id="other_issuer"),
        pytest.param(make_claims(exp=None), id="no_exp"),
        pytest.param(make_claims(sub=None), id="no_sub"),
    ],
)
def test_verify_rejects_claims(
    jwt_token_verifier: JwtTokenVerifier, signing_key: rsa.RSAPrivateKey, claims: dict[str, object]
) -> None:
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": KEY_ID})

    with pytest.raises(InvalidCredentialsError, match="Credentials rejected"):
        jwt_token_verifier.verify(token)


def test_verify_rejects_unknown_kid_as_invalid_credentials(
    jwt_token_verifier: JwtTokenVerifier, signing_key: rsa.RSAPrivateKey
) -> None:
    token = jwt.encode(make_claims(), signing_key, algorithm="RS256", headers={"kid": "retired"})

    with pytest.raises(InvalidCredentialsError, match="PyJWKClientError"):
        jwt_token_verifier.verify(token)
```

- **The forged tokens are built by hand.** `alg` `none` comes from
  `jwt.encode(claims, "", algorithm="none")`; an `HS256` token signed with the public PEM does not,
  because `jwt.encode` refuses that key as an HMAC secret — sign `header.payload` with
  `hmac.digest(public_pem, ..., hashlib.sha256)` and base64url-encode the three parts yourself.
- **PyJWT reads the wall clock itself**, with no seam to inject one: issue test tokens relative to
  now, and put an expired token's `exp` well past the leeway rather than a second before it.
- **These tests start a local HTTP server**, so they carry the integration marker; the unit run
  keeps the fake (`python-auth`).
