# Testing the JWT Verifier

## Contents

- The contract harness: a generated key and a local key set
- PyJWT's rejections as one parametrized test, the unknown `kid` on its own
- Forged tokens built by hand; the wall clock PyJWT reads

The contract suite and its harness type are `python-auth`; `pytest-httpserver` is `python-pytest`.
These tests start a local HTTP server, so they carry the integration marker; the unit run keeps the
fake.

### The JWT harness generates a key once, serves its public half, and goes offline by answering 503

**Why:** the contract suite needs to issue a token and take the key set away for every
implementation; for JWT that is a real RSA key and a real key set endpoint, so the verifier under
test fetches over HTTP exactly as in production.

**Example:**
```python
# WRONG — the verifier is handed a key directly, so the key set fetch is never exercised
@pytest.fixture
def jwt_token_verifier_harness(signing_key: rsa.RSAPrivateKey) -> TokenVerifierHarness:
    verifier = StaticKeyVerifier(signing_key.public_key(), audience=AUDIENCE, issuer=ISSUER)
    return TokenVerifierHarness(
        verifier=verifier,
        issue_token=lambda principal: issue_jwt(signing_key, principal),
        take_key_set_offline=lambda: None,
    )


# CORRECT — a local key set the verifier fetches, and an outage it can be given
@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwt_token_verifier_harness(
    httpserver: HTTPServer, signing_key: rsa.RSAPrivateKey
) -> TokenVerifierHarness:
    public_jwk = RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    key_set = {"keys": [public_jwk | {"kid": KEY_ID, "use": "sig", "alg": "RS256"}]}
    httpserver.expect_request(_JWKS_PATH).respond_with_data(
        json.dumps(key_set), content_type="application/json"
    )
    verifier = JwtTokenVerifier(
        build_signing_keys(httpserver.url_for(_JWKS_PATH)), audience=AUDIENCE, issuer=ISSUER
    )

    def take_key_set_offline() -> None:
        httpserver.clear_all_handlers()
        httpserver.expect_request(_JWKS_PATH).respond_with_data("", status=503)

    return TokenVerifierHarness(
        verifier=verifier,
        issue_token=lambda principal: issue_jwt(signing_key, principal),
        take_key_set_offline=take_key_set_offline,
    )
```

### PyJWT's rejections are one parametrized test, and the unknown `kid` is a test of its own

**Why:** each case asserts `InvalidCredentialsError`; the unknown `kid` stands apart because it is
the one an `except InvalidTokenError` lets through. PyJWT reads the wall clock itself, with no seam,
so test tokens are issued relative to now and an expired one sits well past the leeway.

**Example:**
```python
# WRONG — one rejection tested, and the expiry one second past now, inside the leeway
def test_verify_rejects_expired_token(
    jwt_token_verifier: JwtTokenVerifier, signing_key: rsa.RSAPrivateKey
) -> None:
    claims = make_claims(exp=int(time.time()) - 1)
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": KEY_ID})

    with pytest.raises(InvalidCredentialsError):
        jwt_token_verifier.verify(token)


# CORRECT — every claim rejection in one table, the expiry past the leeway, and the kid apart
@pytest.mark.parametrize(
    "claims",
    [
        pytest.param(make_claims(exp=int(time.time()) - _PAST_LEEWAY_SECONDS), id="expired"),
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

    with pytest.raises(InvalidCredentialsError, match="credentials rejected"):
        jwt_token_verifier.verify(token)


def test_verify_rejects_unknown_kid_as_invalid_credentials(
    jwt_token_verifier: JwtTokenVerifier, signing_key: rsa.RSAPrivateKey
) -> None:
    token = jwt.encode(make_claims(), signing_key, algorithm="RS256", headers={"kid": "retired"})

    with pytest.raises(InvalidCredentialsError, match="PyJWKClientError"):
        jwt_token_verifier.verify(token)
```

### A forged token is built by hand, because `jwt.encode` refuses to forge one

**Why:** `alg` `none` comes from `jwt.encode(claims, "", algorithm="none")`, but an `HS256` token
signed with the public PEM does not — `jwt.encode` refuses that key as an HMAC secret, so the test
signs `header.payload` with `hmac.digest` and base64url-encodes the parts itself.

**Example:**
```python
# WRONG — raises InvalidKeyError in the test itself, so the verifier is never tried
def forge_hs256_with_public_key(claims: Mapping[str, object], public_pem: bytes) -> str:
    return jwt.encode(dict(claims), public_pem, algorithm="HS256")


# CORRECT — the confused-algorithm token assembled by hand
def forge_hs256_with_public_key(claims: Mapping[str, object], public_pem: bytes) -> str:
    header = _base64url(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KEY_ID}).encode())
    payload = _base64url(json.dumps(claims).encode())
    signature = hmac.digest(public_pem, f"{header}.{payload}".encode(), hashlib.sha256)
    return f"{header}.{payload}.{_base64url(signature)}"
```
