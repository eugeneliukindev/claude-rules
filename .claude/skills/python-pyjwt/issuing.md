# Issuing

### A token is signed with its `kid` in the header, and its times come from the injected clock

**Why:** without `kid` a verifier cannot pick the key from the key set, and a rotation breaks every
token. `iat` and `exp` may be aware `datetime`s, which PyJWT writes as integer seconds; the `now`
they are computed from is injected (`functions.md`), so a test fixes it. An access token lives
minutes: a JWT cannot be revoked before its `exp`.

**Example:**
```python
# WRONG — no kid, and the wall clock read inside
def sign_member_pass(
    claims: Mapping[str, object],
    *,
    private_key: RSAPrivateKey,
    lifetime: timedelta = _PASS_LIFETIME,
) -> str:
    timed = {**claims, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + lifetime}
    return jwt.encode(timed, private_key, algorithm="RS256")


# CORRECT — the key named, the times from the clock
def sign_member_pass(
    claims: Mapping[str, object],
    *,
    private_key: RSAPrivateKey,
    key_id: str,
    clock: Clock,
    lifetime: timedelta = _PASS_LIFETIME,
) -> str:
    now = clock.now()
    timed = {**claims, "iat": now, "exp": now + lifetime}
    return jwt.encode(timed, private_key, algorithm="RS256", headers={"kid": key_id})
```
