# Issuing

What an issued token carries and how long it lives is `python-auth`.

### A token is signed with its `kid` in the header, and its times come from the injected clock

**Why:** without `kid` a verifier cannot pick the key from the key set, and a rotation breaks every
token. `iat` and `exp` may be aware `datetime`s, which PyJWT writes as integer seconds; the `now`
they are computed from is injected (`functions.md`), so a test fixes it.

**Example:**
```python
# WRONG — no kid, and the wall clock read inside
def issue_access_token(claims: Mapping[str, object], *, private_key: RSAPrivateKey) -> str:
    timed = {**claims, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + _ACCESS_LIFETIME}
    return jwt.encode(timed, private_key, algorithm="RS256")


# CORRECT — the key named, the times from the clock
def issue_access_token(
    claims: Mapping[str, object], *, private_key: RSAPrivateKey, key_id: str, clock: Clock
) -> str:
    now = clock.now()
    timed = {**claims, "iat": now, "exp": now + _ACCESS_LIFETIME}
    return jwt.encode(timed, private_key, algorithm="RS256", headers={"kid": key_id})
```
