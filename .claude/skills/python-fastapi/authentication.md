# Authentication in FastAPI

## Contents

- The dependency that turns a bearer token into a `Principal`
- `set_cookie` with every flag set
- Routes tested through the app with the fake verifier

What a verifier must do — the contract, the two errors, 401 against 403 against 503, a fixed body —
is `python-auth`; this file is how a FastAPI app carries it out.

### `require_principal` is a plain `def` mapping the verifier's errors to a fixed 401 and a 503

**Why:** `verify` may block on a key set fetch, so the dependency is a `def` that FastAPI runs in
its thread pool (`python-pyjwt`). `HTTPBearer` already answers a missing header with a 401 and
`WWW-Authenticate`; the verifier's rejection must match it, with one fixed body, the reason left on
the chained cause. `HTTPException` is right here: authentication failing exists only in HTTP. The
root builds the verifier, the lifespan yields it, and the dependency sits on the protected router.

**Example:**
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

### `set_cookie` sets `secure`, `httponly` and `samesite` on purpose

**Why:** Starlette's `set_cookie` defaults to `secure=False` and `httponly=False`, so a session
cookie set with the defaults is readable by any script on the page and sent over plain HTTP. A
`__Host-` name works with Starlette's defaults of `Path=/` and no `Domain`.

### Protected routes are tested through the app built with the fake verifier

**Why:** a principal injected with `dependency_overrides` skips the edge's mapping; through the app,
a token from the fake's `issue` gets through, `"Bearer forged"` gets the fixed 401 with
`WWW-Authenticate`, and `is_key_set_reachable = False` gets the 503.

**Example:**
```python
# WRONG — the dependency is overridden, so the 401 and 503 mapping is never exercised
def test_document_route_rejects_forged_token(app: FastAPI) -> None:
    app.dependency_overrides[require_principal] = lambda: _OWNER
    with TestClient(app) as client:
        response = client.get(f"/documents/{_DOCUMENT_ID}", headers=_FORGED_BEARER)

    assert response.status_code == HTTPStatus.OK


# CORRECT — the real dependency runs against the fake verifier
def test_document_route_rejects_forged_token(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get(f"/documents/{_DOCUMENT_ID}", headers=_FORGED_BEARER)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid bearer token"}
```
