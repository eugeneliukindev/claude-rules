---
name: python-security
description: >-
  Handles input from outside and who may act on it: parameterized SQL, safe parsers, paths, uploads,
  archives, SSRF, size limits, passwords, tokens, permissions. ALWAYS invoke this skill when code
  handles a request body, a filename, an upload, a URL, an Authorization header or a cookie, or
  checks a role or an owner. Do not handle such input directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Security

This covers input from outside the process and who may act on what it asks for, whatever library reads it. Where a secret lives is `python-wiring`; keeping it out of a `repr` is `types.md`.

## Untrusted Data

- **Parameterize SQL, and take an identifier from an allowlist of constants.** A value interpolated into SQL text writes SQL, and an `ORDER BY` column or a table name cannot be a bound parameter; pass a list of values as one parameter too, never a joined string.
- **Parse an untrusted document with the safe parser.** Use `yaml.safe_load`, never `yaml.Loader` or `FullLoader`, which call or resolve whatever a tag names; parse XML through `defusedxml`, which refuses entity expansion and external entities.
- **Never `eval`, `exec` or `pickle.loads` outside data.** Use `ast.literal_eval` when the input really is a Python literal.
- **Bound every external input in size, decompression included.** Validation covers size, not just shape: a body, a page, a collection, a decompressed stream; deflate packs about a thousand to one.
- **Inflate at most one byte past the limit and refuse that, then refuse a stream that did not reach its end.** A stream cut short inflates without an error, so without the end check a prefix passes as the whole document.

## Decisions That Fail Closed

- **Make a permission check allow what it lists, never deny a list.** A denylist allows every role added after it.
- **Deny or raise when a lookup inside a permission check fails, and never catch it into an allow.**
- **Compare a secret with `hmac.compare_digest`, never `==`.** `==` stops at the first differing byte, so the response time tells an attacker how much of a guess was right.

## Passwords

- **Hash a password with Argon2id through `argon2-cffi`, never a fast hash.** A fast hash like `sha256` lets a leaked table be tested at billions of guesses a second; `argon2.PasswordHasher` salts, is slow by design, raises on a mismatch, and its `check_needs_rehash` upgrades old hashes at the next login.
- **Where no dependency is allowed, use `hashlib.scrypt` with every parameter stated, `maxmem` included, and store the salt beside the hash.** OpenSSL's default ceiling of 32 MiB fails `n=2**15, r=8, p=1` with `memory limit exceeded`.

## Paths, Uploads and Archives

- **Resolve a path from outside input, then check it against its base with `is_relative_to`, never a string prefix.** `resolve()` removes `..` and follows symlinks, and `is_relative_to` compares components, so a sibling directory sharing the prefix fails.
- **Store an upload under a generated name, and keep the user's filename as data for display.** The user's name as a path is `..`, a device name or another upload's name.
- **Extract a tar archive with `filter="data"`.** It refuses absolute paths, `..`, links leaving the destination and device files; it is the default from 3.14, and below that the argument is mandatory.

## URLs From Outside

- **Fetch a URL from a user only if it passes an allowlist of schemes and hosts, and block internal metadata ranges and loopback by default.**
- **Check every address the host name resolves to, on every hop, and require each to be global.** A public name whose DNS answers with the metadata address passes every check of the string.
- **Follow redirects by hand, bound the chain, and request the address you checked.** A client that follows a redirect on its own skips the allowlist, and a second lookup can answer differently; an egress proxy enforcing the same rule closes that gap.

## A Token Becomes a Caller

- **Verify tokens through one contract whose `verify(token)` returns a frozen caller, or raises a rejected-credentials or an unreachable-signing-keys error.** Rejected covers malformed, forged, expired, another audience and an unknown key; both errors fail closed.
- **Translate every library exception inside the verifier implementation, the only module importing its library.**
- **Hand a service the verified caller, never the token or the claims.** A service handed the token decodes it again with its own idea of the algorithms, and one handed the claims trusts whatever dict it gets.
- **Believe nothing in a token before its signature: not the algorithm its header names, not a key URL in it (`jku`, `x5u`), not its `sub`.** Pin the algorithms in a JWT implementation, and require the audience, the issuer and an expiry.
- **Validate the decoded claims as a boundary payload, but ignore extra claims rather than refuse them.** The claim set is the identity provider's contract, which adds claims without telling you.

## Authorization

- **Let the edge establish who is calling for every route but the reviewed public ones, and check access to a resource in the service.** The edge has not loaded the resource; a route guarded by "is logged in" or a role lets every caller read every resource whose id they can guess, opaque ids or not.
- **Check access next to the load for one resource, and in the query for a list.** A list filtered after the query leaks through pagination counts and totals, so the repository takes the caller.
- **Answer someone else's resource exactly like a missing one where existence is itself the secret.** A 403 confirms the id.
- **Raise a permission error, mapped to 403 at the edge, for a caller who may see a resource but not act on it.** Choose not-found or forbidden per resource; a scope or a role is a coarse gate the edge may check first, and ownership is the fine one the service always checks.

## Rejections

- **Answer no valid credentials with 401 and `WWW-Authenticate: Bearer`, a valid caller refused with 403, and unreachable signing keys with 503.** A key set outage answered as 401 makes every client drop its session.
- **Give every rejected token the same body.** Distinct messages tell someone probing with a stolen token which checks passed.
- **Record the rejection reason on the server, as the chained cause and a counter with a `reason` attribute, at `INFO` at most.** A rejection is an expected client mistake.
- **Send a token in a header, never a query string.** A query string lands in proxy logs and browser history.
- **Make the access log record an allowlist of headers, never a denylist.** A denylist misses the next header that carries a credential; a span's attributes are a log too, so put the caller's id there, never the claims (`logging.md`).
- **Make a browser session an opaque id from `secrets.token_urlsafe`, not a JWT.**
- **Set a session cookie `Secure`, `HttpOnly`, `SameSite` and `__Host-`-prefixed, since frameworks default to none of it.** Without `Secure` it travels over plain HTTP, without `HttpOnly` any script on the page reads it, and the `__Host-` prefix makes the browser refuse it unless it is `Secure`, has `Path=/` and no `Domain`; `SameSite` never replaces CSRF protection for state-changing requests.

## Issuing Tokens and Guarding Credentials

- **Prefer an identity provider to issuing tokens yourself.**
- **Give an access token a lifetime of minutes, and `iss`, `aud`, `sub`, `iat`, `exp`, `jti` and `kid`.** A JWT cannot be revoked before its `exp`; take `jti` from `secrets`, let `kid` name the signing key, and inject the clock (`functions.md`).
- **Make a refresh token opaque, store it hashed, and rotate it on every use.** One presented a second time was copied, so revoke its whole family; a password-reset token is single-use, short-lived, hashed and consumed in the transaction that changes the password.
- **Rotate a signing key through the key set: publish, wait the cache lifetime, sign, retire.** Verifiers cache the key set; keep the old key published until its last token has expired.
- **Count attempts at a credential endpoint per account and per source, in the shared cache with the window as its TTL.** A counter in the process is one per worker and restarts with it.

## Service-to-Service Credentials

- **Give each service its own credential: a client-credentials token, a workload identity or mutual TLS.** One shared static key cannot be rotated without a coordinated deploy or revoked for one caller.
- **Make a service token's `aud` name the receiving service.** A token minted for one service and replayed against another is then rejected.
- **Never forward a user's token across a trust boundary.** Inside one, the next service verifies it with its own audience in the list or exchanges it; across one, call with the service's own credential.
- **Fetch an outbound token once, keep it in the client object the root owns, and renew it a safety margin before its `exp`.** Fetched per request, every call pays the identity provider's round trip and rate limit; cached past `exp`, every call fails.

## Testing

- **Give the fake verifier opaque tokens it issued and mapped to callers, and a way to lose its keys.** A fake that accepts every token lets no test reach a rejection.
- **Run one contract suite over every verifier, with each fixture handing it a harness that issues tokens and cuts off the signing keys.** The suite also expects a rejected-credentials error for a token nobody issued; a rejection only one implementation can produce, like an expired JWT or `alg` `none`, is its own test.
- **Test authorization at the service, with the owner and with another caller.** A test with only the owner passes a service that checks nothing.
