# Issuing Tokens and Guarding Credentials

## Contents

- Access tokens live minutes and carry every claim a verifier needs
- Refresh tokens are opaque, hashed and rotated
- Signing keys rotate through the key set
- Credential endpoints are rate-limited in the shared cache

Prefer an identity provider; this file is for a service that issues its own tokens.

### An access token lives minutes, and carries `iss`, `aud`, `sub`, `iat`, `exp`, `jti` and `kid`

**Why:** a JWT cannot be revoked before its `exp`, so its lifetime is how long a stolen one works.
`jti` comes from `secrets`, `kid` names the key that signed it, and the clock is injected
(`functions.md`).

**Example:**
```python
# WRONG — a day-long token without an audience, a key id or an id of its own
def access_claims(user_id: UserId, *, now: datetime) -> dict[str, object]:
    return {"sub": user_id, "exp": now + timedelta(days=1)}


# CORRECT — minutes, and every claim a verifier checks
def access_claims(
    user_id: UserId, *, now: datetime, issuer: str, audience: str
) -> dict[str, object]:
    return {
        "iss": issuer,
        "aud": audience,
        "sub": user_id,
        "iat": now,
        "exp": now + _ACCESS_TOKEN_LIFETIME,
        "jti": secrets.token_urlsafe(_TOKEN_ID_BYTES),
    }
```

### A refresh token is opaque, stored hashed, and rotated on every use

**Why:** a refresh token presented a second time means it was copied: the whole family it belongs to
is revoked, not just that token. Stored hashed, a database leak does not hand out live tokens. A
password-reset token is the same: single-use, short-lived, hashed, consumed in the transaction that
changes the password.

**Example:**
```python
# WRONG — reusable, stored as is: a copied token works as long as the original
async def refresh(token: str, *, refresh_tokens: RefreshTokens) -> TokenPair:
    family = await refresh_tokens.family_of(token)
    return await refresh_tokens.issue_access(family)


# CORRECT — a replay revokes the family; a valid use is consumed and replaced
async def refresh(token: str, *, refresh_tokens: RefreshTokens) -> TokenPair:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    family = await refresh_tokens.consume(token_hash)
    if family.was_already_used:
        await refresh_tokens.revoke_family(family.family_id)
        raise InvalidCredentialsError("refresh token reused")
    return await refresh_tokens.rotate(family.family_id)
```

### A signing key rotates through the key set: publish, wait the cache lifetime, sign, retire

**Why:** verifiers cache the key set; a key used to sign before they fetched it fails every token
until their caches expire. The old key stays published until its last token has expired.

**Example:**
```python
# WRONG — the new key signs at once; every verifier with a cached key set rejects its tokens
async def rotate_signing_key(*, keys: SigningKeys) -> None:
    new_key = await keys.generate()
    await keys.make_current(new_key.key_id)


# CORRECT — published first, used only after the verifiers' cache lifetime has passed
async def rotate_signing_key(*, keys: SigningKeys, clock: Clock) -> None:
    new_key = await keys.generate()
    await keys.publish(new_key.key_id)
    await keys.schedule_current(new_key.key_id, at=clock.now() + _VERIFIER_KEY_CACHE_LIFETIME)
```

### A login, reset or token endpoint is rate-limited per account and per source, in the shared cache

**Why:** a counter in the process is one per worker and starts afresh on every restart — four
workers grant four times the attempts. The counter lives in the shared cache with the window as its
TTL (`python-caching`).

**Example:**
```python
# WRONG — counted in this process: each of four workers grants its own five attempts per account
_attempts_by_email: Counter[str] = Counter()


async def log_in(credentials: Credentials, *, passwords: PasswordChecker) -> UserId:
    _attempts_by_email[credentials.email] += 1
    if _attempts_by_email[credentials.email] > _LOGIN_ATTEMPTS:
        raise TooManyAttemptsError(credentials.email)
    return await passwords.check(credentials)


# CORRECT — one shared count per account and one per source, each expiring with its window
async def log_in(
    credentials: Credentials,
    *,
    source: IPv4Address | IPv6Address,
    limiter: RateLimiter,
    passwords: PasswordChecker,
) -> UserId:
    account_key = f"login:account:{credentials.email}"
    await limiter.consume(account_key, limit=_LOGIN_ATTEMPTS, window=_LOGIN_WINDOW)
    await limiter.consume(f"login:source:{source}", limit=_SOURCE_ATTEMPTS, window=_LOGIN_WINDOW)
    return await passwords.check(credentials)
```
