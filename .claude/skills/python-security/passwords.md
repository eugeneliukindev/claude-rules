# Passwords

### A password is hashed with Argon2id, or scrypt with every parameter stated

**Why:** a fast hash such as `sha256` lets a leaked table be tested at billions of guesses a second.
`argon2.PasswordHasher` from `argon2-cffi` salts, is slow by design, raises on a mismatch, and its
`check_needs_rehash` upgrades old hashes at the next login. Where no dependency is allowed,
`hashlib.scrypt` with `n=2**15, r=8, p=1` needs `maxmem` — OpenSSL's default ceiling is 32 MiB, and
those parameters fail with `memory limit exceeded` — and the salt is stored beside the hash.

**Example:**
```python
# WRONG — a fast hash: a leaked table is tested at billions of guesses a second
def is_customer_password_correct(password_hash: str, password: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), password_hash)


# CORRECT — Argon2id, salted and slow by design; a corrupt hash raises rather than matching
def is_customer_password_correct(
    password_hash: str, password: str, *, hasher: PasswordHasher
) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
```
