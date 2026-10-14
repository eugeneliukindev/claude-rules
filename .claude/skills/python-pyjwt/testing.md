# Testing the JWT Verifier

## Contents

- A generated key and a local key set the verifier fetches
- PyJWT's rejections as one parametrized test; the unknown `kid` and the outage on their own
- Forged tokens built by hand; the wall clock PyJWT reads

These tests start a local HTTP server with `pytest-httpserver`, so they carry the integration
marker.

### The key is generated once, its public half served as a key set the verifier fetches

**Why:** a verifier handed a key directly never exercises the fetch — the `kid` lookup, the cache,
the outage — which is where the classification of errors lives; a real RSA key behind a real key
set endpoint runs it exactly as in production.

**Example:**
```python
# WRONG — the verifier is handed a key directly, so the key set fetch is never exercised
@pytest.fixture
def member_pass_verifier(signing_key: rsa.RSAPrivateKey) -> StaticKeyMemberPassVerifier:
    return StaticKeyMemberPassVerifier(
        public_key=signing_key.public_key(), audience=AUDIENCE, issuer=ISSUER
    )


# CORRECT — a local key set the verifier fetches over HTTP
@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def member_pass_verifier(
    httpserver: HTTPServer, signing_key: rsa.RSAPrivateKey
) -> MemberPassVerifier:
    public_jwk = RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    key_set = {"keys": [public_jwk | {"kid": KEY_ID, "use": "sig", "alg": "RS256"}]}
    httpserver.expect_request(_JWKS_PATH).respond_with_data(
        json.dumps(key_set), content_type="application/json"
    )
    signing_keys = build_member_signing_keys(httpserver.url_for(_JWKS_PATH))
    return MemberPassVerifier(signing_keys=signing_keys, audience=AUDIENCE, issuer=ISSUER)
```

### PyJWT's rejections are one parametrized test; the unknown `kid` and the outage stand apart

**Why:** each claim case asserts the rejected-token error; the unknown `kid` stands apart because it
is the one an `except InvalidTokenError` lets through, and the outage — the key set answering 503 —
because it expects the other error. PyJWT reads the wall clock itself, with no seam, so test tokens
are issued relative to now and an expired one sits well past the leeway.

**Example:**
```python
# WRONG — one rejection tested, and the expiry one second past now, inside the leeway
def test_verify_rejects_expired_token(
    member_pass_verifier: MemberPassVerifier, signing_key: rsa.RSAPrivateKey
) -> None:
    claims = gym_claims(exp=int(time.time()) - 1)
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": KEY_ID})

    with pytest.raises(MemberTokenRejectedError):
        member_pass_verifier.verify(token)


# CORRECT — every claim rejection in one table, the expiry past the leeway, the kid and outage apart
@pytest.mark.parametrize(
    "claims",
    [
        pytest.param(gym_claims(exp=int(time.time()) - _PAST_LEEWAY_SECONDS), id="expired"),
        pytest.param(gym_claims(aud="https://lockers.gym.example.com"), id="other_audience"),
        pytest.param(gym_claims(iss="https://other-issuer.example.com/"), id="other_issuer"),
        pytest.param(gym_claims(exp=None), id="no_exp"),
        pytest.param(gym_claims(sub=None), id="no_sub"),
    ],
)
def test_verify_rejects_claims(
    member_pass_verifier: MemberPassVerifier,
    signing_key: rsa.RSAPrivateKey,
    claims: dict[str, object],
) -> None:
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": KEY_ID})

    with pytest.raises(MemberTokenRejectedError, match="member token rejected"):
        member_pass_verifier.verify(token)


def test_verify_rejects_unknown_kid(
    member_pass_verifier: MemberPassVerifier, signing_key: rsa.RSAPrivateKey
) -> None:
    token = jwt.encode(gym_claims(), signing_key, algorithm="RS256", headers={"kid": "retired"})

    with pytest.raises(MemberTokenRejectedError, match="PyJWKClientError"):
        member_pass_verifier.verify(token)


def test_verify_reports_key_set_outage_as_unreachable(
    member_pass_verifier: MemberPassVerifier,
    signing_key: rsa.RSAPrivateKey,
    httpserver: HTTPServer,
) -> None:
    token = jwt.encode(gym_claims(), signing_key, algorithm="RS256", headers={"kid": KEY_ID})
    httpserver.clear_all_handlers()
    httpserver.expect_request(_JWKS_PATH).respond_with_data("", status=503)

    with pytest.raises(MembershipKeysUnreachableError, match="could not be fetched"):
        member_pass_verifier.verify(token)
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
    header = _b64url_segment(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KEY_ID}).encode())
    payload = _b64url_segment(json.dumps(claims).encode())
    signature = hmac.digest(public_pem, f"{header}.{payload}".encode(), hashlib.sha256)
    return f"{header}.{payload}.{_b64url_segment(signature)}"
```
