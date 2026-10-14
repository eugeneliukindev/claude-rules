# Authentication in FastAPI

What a token verifier must check, and when a request is a 401, a 403 or a 503, is `python-auth`.

### The bearer dependency is a plain `def` that turns every rejection into one fixed 401

**Why:** verifying may block on a key set fetch, so the dependency is a `def` that FastAPI runs in
its thread pool. `HTTPBearer` — the alias here is `Annotated[HTTPAuthorizationCredentials,
Depends(HTTPBearer())]` — already answers a missing header with a 401 and `WWW-Authenticate:
Bearer`; a rejected token gets the same, with one fixed body — a body naming the failed check tells
a forger which check passed — and the reason stays on the chained cause. An unreachable key set is a
503: the token may be fine. `HTTPException` is right here, since authentication exists only in
HTTP. The lifespan yields the verifier, and the dependency sits on the protected router.

**Example:**
```python
# WRONG — the body names the failed check: "audience mismatch" says the signature was good
def authenticate_rider(request: Request, bearer: RiderBearer) -> Rider:
    verifier: RiderTokenVerifier = request.state.rider_tokens
    try:
        return verifier.verify(bearer.credentials)
    except RiderTokenRejectedError as error:
        raise HTTPException(
            HTTPStatus.UNAUTHORIZED, error.reason, headers={"WWW-Authenticate": "Bearer"}
        ) from error
    except SigningKeysUnreachableError as error:
        raise HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, "Try again later") from error


# CORRECT — one fixed body for every rejected token; the reason stays on the chained cause
def authenticate_rider(request: Request, bearer: RiderBearer) -> Rider:
    verifier: RiderTokenVerifier = request.state.rider_tokens
    try:
        return verifier.verify(bearer.credentials)
    except RiderTokenRejectedError as error:
        raise HTTPException(
            HTTPStatus.UNAUTHORIZED, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"}
        ) from error
    except SigningKeysUnreachableError as error:
        raise HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, "Try again later") from error
```

### `set_cookie` sets `secure`, `httponly` and `samesite` on purpose

**Why:** Starlette's `set_cookie` defaults to `secure=False`, `httponly=False` and `samesite="lax"`,
so a session cookie set with the defaults is readable by any script on the page and sent over plain
HTTP. A `__Host-` name works with Starlette's defaults of `Path=/` and no `Domain`.

### Protected routes are tested through the app built with a fake verifier

**Why:** a rider injected with `dependency_overrides` skips the mapping above; through the app, a
token the fake issued gets through, `"Bearer forged"` gets the fixed 401 with `WWW-Authenticate`,
and a fake set to unreachable gets the 503.

**Example:**
```python
# WRONG — the dependency is overridden, so the 401 and 503 mapping is never exercised
def test_ride_history_rejects_forged_token(app: FastAPI) -> None:
    app.dependency_overrides[authenticate_rider] = lambda: _RIDER
    with TestClient(app) as client:
        response = client.get("/riders/me/rides", headers=_FORGED_BEARER)

    assert response.status_code == HTTPStatus.OK


# CORRECT — the real dependency runs against the fake verifier
def test_ride_history_rejects_forged_token(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/riders/me/rides", headers=_FORGED_BEARER)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid bearer token"}
```
