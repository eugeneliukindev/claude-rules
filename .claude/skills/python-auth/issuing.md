# Issuing Tokens and Guarding Credentials

## Contents

- Access tokens live minutes and carry every claim a verifier needs
- Refresh tokens are opaque, hashed and rotated
- Signing keys rotate through the key set
- Credential endpoints count attempts in the shared cache

Prefer an identity provider.

### An access token lives minutes, and carries `iss`, `aud`, `sub`, `iat`, `exp`, `jti` and `kid`

**Why:** a JWT cannot be revoked before its `exp`, so its lifetime is how long a stolen one works.
`jti` comes from `secrets`, `kid` names the key that signed it, and the clock is injected
(`functions.md`).

### A refresh token is opaque, stored hashed, and rotated on every use

**Why:** a refresh token presented a second time means it was copied: the whole family it belongs to
is revoked, not just that token. Stored hashed, a database leak does not hand out live tokens. A
password-reset token is the same: single-use, short-lived, hashed, consumed in the transaction that
changes the password.

**Example:**
```python
# WRONG — reusable, stored as is: a copied token works as long as the original
async def exchange_refresh_token(token: str, *, refresh_grants: RefreshGrants) -> IssuedTokens:
    family = await refresh_grants.family_of(token)
    return await refresh_grants.issue_access(family)


# CORRECT — a replay revokes the family; a valid use is consumed and replaced
async def exchange_refresh_token(token: str, *, refresh_grants: RefreshGrants) -> IssuedTokens:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    family = await refresh_grants.consume(token_hash)
    if family.was_already_used:
        await refresh_grants.revoke_family(family.family_id)
        raise RejectedCredentialsError("refresh token reused")
    return await refresh_grants.rotate(family.family_id)
```

### A signing key rotates through the key set: publish, wait the cache lifetime, sign, retire

**Why:** verifiers cache the key set; a key used to sign before they fetched it fails every token
until their caches expire. The old key stays published until its last token has expired.

**Example:**
```python
# WRONG — the new key signs at once; every verifier with a cached key set rejects its tokens
async def rotate_signing_key(*, keys: PortalSigningKeys) -> None:
    new_key = await keys.generate()
    await keys.make_current(new_key.key_id)


# CORRECT — published first, used only after the verifiers' cache lifetime has passed
async def rotate_signing_key(
    *,
    keys: PortalSigningKeys,
    now: datetime,
    verifier_cache_lifetime: timedelta = _VERIFIER_KEY_CACHE_LIFETIME,
) -> None:
    new_key = await keys.generate()
    await keys.publish(new_key.key_id)
    await keys.schedule_current(new_key.key_id, at=now + verifier_cache_lifetime)
```

### A credential endpoint counts attempts per account and per source, in the shared cache

**Why:** a sign-in, reset or token endpoint is guessed against; a counter in the process is one per worker and starts afresh on every restart — four
workers grant four times the attempts. The counter lives in the shared cache with the window as its
TTL.

**Example:**
```python
# WRONG — counted in this process: each of four workers grants its own five attempts per guardian
_attempts_by_email: Counter[str] = Counter()


async def sign_in_guardian(
    form: SignInForm, *, passwords: GuardianPasswords, account_attempts: int = _SIGN_IN_ATTEMPTS
) -> PersonId:
    _attempts_by_email[form.email] += 1
    if _attempts_by_email[form.email] > account_attempts:
        raise SignInThrottledError(form.email)
    return await passwords.check(form)


# CORRECT — one shared count per account and one per source, each expiring with its window
async def sign_in_guardian(
    form: SignInForm,
    *,
    source: IPv4Address | IPv6Address,
    attempts: AttemptBudget,
    passwords: GuardianPasswords,
    account_attempts: int = _SIGN_IN_ATTEMPTS,
    source_attempts: int = _SOURCE_ATTEMPTS,
    window: timedelta = _SIGN_IN_WINDOW,
) -> PersonId:
    account_key = f"sign-in:account:{form.email}"
    await attempts.spend(account_key, limit=account_attempts, window=window)
    await attempts.spend(f"sign-in:source:{source}", limit=source_attempts, window=window)
    return await passwords.check(form)
```
