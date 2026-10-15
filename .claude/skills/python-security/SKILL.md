---
name: python-security
description: >-
  Handles input from outside and who may act on it: parameterized SQL, subprocess arguments, safe
  parsers, paths, uploads, archives, SSRF, size limits, passwords, tokens, permissions. ALWAYS
  invoke this skill when code handles a request body, a filename, an upload, a URL, an Authorization
  header, a cookie or a subprocess argument, or checks a role or an owner. Do not handle such input
  directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Security

Input from outside the process, and who may act on what it asks for, whatever library reads it:
untrusted data, decisions that fail closed, authentication, authorization, issued tokens and service
credentials. The rules name the function, because the function is what gets copied. Where a secret
lives is `python-wiring`; keeping it out of a `repr` and a `LiteralString` check are `python-types`.

## Untrusted Data

### SQL is parameterized, and an identifier comes from an allowlist of constants

**Why:** a value interpolated into SQL text writes SQL; an `ORDER BY` column or a table name cannot
be a bound parameter, so it is one of a fixed set of constants. A list of values is one parameter
too, never a joined string.

**Example:**
```python
# WRONG — the sort column arrives from the query string, so the query string writes SQL
def queued_print_jobs(
    press_id: int, *, connection: sqlite3.Connection, sort_by: str
) -> list[tuple[int, str]]:
    query = f"SELECT job_id, title FROM print_jobs WHERE press_id = ? ORDER BY {sort_by}"
    return connection.execute(query, (press_id,)).fetchall()

# CORRECT — the clause is one of two constants; only the value travels as a parameter
_PRINT_JOB_ORDER: Final = MappingProxyType(
    {PrintJobSort.NEWEST: "queued_at DESC", PrintJobSort.OLDEST: "queued_at ASC"}
)

def queued_print_jobs(
    press_id: int, *, connection: sqlite3.Connection, sort_by: PrintJobSort
) -> list[tuple[int, str]]:
    order_clause = _PRINT_JOB_ORDER[sort_by]
    query = (
        "SELECT job_id, title FROM print_jobs WHERE press_id = ?"
        f" ORDER BY {order_clause}"  # noqa: S608  # allowlisted identifier
    )
    return connection.execute(query, (press_id,)).fetchall()
```

### An untrusted document is parsed by the safe parser, and nothing from outside is evaluated

**Why:** `yaml.load(..., Loader=yaml.Loader)` calls whatever a `!!python/object/apply` tag names,
and `FullLoader` — which refuses those tags — still resolves `!!python/name` references to anything
already imported, a surface `safe_load` does not have. XML goes through `defusedxml`, which refuses
entity expansion and external entities. No `eval`, `exec` or `pickle.loads` on outside data;
`ast.literal_eval` when the input really is a Python literal.

### Every external input is bounded in size, decompression included

**Why:** validation includes size, not just shape — a body, a page, a collection, a decompressed
stream. Deflate packs about a thousand to one, so a megabyte of gzip becomes a gigabyte in memory.
A stream cut short inflates without an error — half a gzip payload returned 4 bytes of 10,023 and
`eof` stayed `False` — so the prefix would be handed on as the whole document without the last
check.

**Example:**
```python
# WRONG — inflates whatever the artwork expands to
def inflate_artwork(compressed: bytes) -> bytes:
    return gzip.decompress(compressed)

# CORRECT — inflate at most one byte past the limit, refuse that, and refuse a truncated stream
def inflate_artwork(compressed: bytes, *, max_bytes: int = _MAX_ARTWORK_BYTES) -> bytes:
    inflater = zlib.decompressobj(wbits=_GZIP_WBITS)
    artwork = inflater.decompress(compressed, max_bytes + 1)
    if len(artwork) > max_bytes:
        raise ArtworkTooLargeError(max_bytes)
    if not inflater.eof:
        raise TruncatedArtworkError(len(compressed))
    return artwork
```

## Decisions That Fail Closed

### A permission check allows what it lists, and an error inside it denies

**Why:** a check that denies a list of roles allows every role added after it; one that allows a
list denies them. A lookup that fails inside the check — the store holding the roles times out —
raises or denies, and nothing catches it into an allow.

**Example:**
```python
# WRONG — denies the roles it lists, so a role added next year may sign off any proof
def can_approve_proof(operator: PressOperator) -> bool:
    return operator.role not in _ROLES_WITHOUT_PROOF_APPROVAL

# CORRECT — allows the roles it lists; every other role, a new one included, is denied
def can_approve_proof(operator: PressOperator) -> bool:
    return operator.role in _PROOF_APPROVING_ROLES
```

### A secret is compared with `hmac.compare_digest`, never `==`

**Why:** `==` stops at the first differing byte, so the response time tells an attacker how much of
a guessed signature was right.

## Passwords

### A password is hashed with Argon2id, or scrypt with every parameter stated

**Why:** a fast hash such as `sha256` lets a leaked table be tested at billions of guesses a second.
`argon2.PasswordHasher` from `argon2-cffi` salts, is slow by design, raises on a mismatch, and its
`check_needs_rehash` upgrades old hashes at the next login. Where no dependency is allowed,
`hashlib.scrypt` with `n=2**15, r=8, p=1` needs `maxmem` — OpenSSL's default ceiling is 32 MiB, and
those parameters fail with `memory limit exceeded` — and the salt is stored beside the hash.

## Paths, Uploads and Archives

### A path from outside input is resolved, then checked component by component against its base

**Why:** a string prefix check passes `../../etc/passwd` and `/srv/proofs-old` alike; `resolve()`
removes `..` and follows symlinks, and `is_relative_to` compares path components, not characters.

**Example:**
```python
# WRONG — "../../etc/passwd" still starts with the root string, and so does "/srv/proofs-old"
def proof_file_path(proof_root: Path, filename: str) -> Path:
    path = proof_root / filename
    if not str(path).startswith(str(proof_root)):
        raise ProofPathEscapeError(filename)
    return path

# CORRECT — resolve ".." and symlinks first, then compare path components
def proof_file_path(proof_root: Path, filename: str) -> Path:
    path = (proof_root / filename).resolve()
    if not path.is_relative_to(proof_root.resolve()):
        raise ProofPathEscapeError(filename)
    return path
```

### An upload is stored under a generated name; the user's name is data for display

**Why:** the user's filename as the path is `..`, a device name, or another upload's name.

### A tar archive is extracted with `filter="data"`

**Why:** an entry named `../../.ssh/authorized_keys` writes wherever it points. The `data` filter
refuses absolute paths, `..`, links leaving the destination and device files; it is the default
from 3.14, and below that the argument is mandatory, because the old default trusted every entry.

## URLs From Outside

A URL from a user is fetched only if it passes an allowlist of schemes and hosts; internal metadata
ranges and loopback are blocked by default.

### Every hop is checked on the addresses its name resolves to, and redirects are followed by hand

**Why:** a public hostname whose DNS answers `169.254.169.254` passes every check of the string, and
the allowlist checked before the first request is worthless once the client follows a redirect there
on its own. Every address the name resolves to must be global, on every hop and before it is
requested, with the chain bounded; the request then goes to the address that was checked, since a
second lookup can answer differently — an egress proxy enforcing the same rule closes that gap.

**Example:**
```python
# WRONG — the name is checked, and a name that resolves to the metadata service passes
def require_public_artwork_url(url: str) -> None:
    host = urlsplit(url).hostname
    if host is None or host in _BLOCKED_HOSTS:
        raise ArtworkUrlRefusedError(url)

# CORRECT — every address the name resolves to must be a public one
def require_public_artwork_url(url: str) -> None:
    host = urlsplit(url).hostname
    if host is None:
        raise ArtworkUrlRefusedError(url)
    for *_, socket_address in socket.getaddrinfo(host, None):
        if not ipaddress.ip_address(socket_address[0]).is_global:
            raise ArtworkUrlRefusedError(url)
```

## A Token Becomes a Caller

### The application verifies tokens through one contract that returns a frozen caller, and a service takes that caller, never the token or the claims

**Why:** the application never sees a token library. `verify(token)` returns who the token speaks
for, or raises one of two errors: rejected credentials — malformed, forged, expired, another
audience, an unknown key: the client's mistake — or unreachable signing keys: the service's
failure. Every library exception is translated inside the implementation, and both fail closed.
Each implementation is the only module importing its library, and the unit tests take a fake. A
service handed the token decodes it again with its own idea of the algorithms; one handed the
claims trusts whatever dict it was given, from a test or a queue message alike; with the caller, a
worker or a test builds it directly.

**Example:**
```python
# WRONG — the service decodes the token itself, with its own idea of the algorithms and errors
@final
class SubmissionDesk:
    def __init__(self, *, submissions: SubmissionStore) -> None:
        self._submissions = submissions

    async def open(self, token: str, submission_id: SubmissionId) -> HomeworkSubmission:
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        return await self._submissions.get_for_pupil(submission_id, pupil_id=claims["sub"])

# CORRECT — one contract, a frozen caller, two classified errors
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class PortalCaller:
    person_id: PersonId
    scopes: frozenset[str]

class PortalAuthenticationError(Exception):
    """Root of the portal authentication package's errors."""

class RejectedCredentialsError(PortalAuthenticationError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"credentials rejected: {reason}")
        self.reason = reason

class SigningKeysUnreachableError(PortalAuthenticationError):
    def __init__(self, key_set_url: str) -> None:
        super().__init__(f"signing keys at {key_set_url} could not be fetched")
        self.key_set_url = key_set_url

class AccessTokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str) -> PortalCaller:
        """Return who the token speaks for, or raise one of this module's errors."""
```

### Nothing in a token is believed before its signature, and its claims model ignores extra claims

**Why:** not the algorithm its header names, not a key URL in it (`jku`, `x5u`), not its `sub`; a
JWT implementation pins its algorithms and requires the audience, the issuer and an expiry. The
decoded claims are a boundary payload, with one carve-out from strict models: the claim set is the
identity provider's contract, which adds claims without telling you, so extra claims are ignored
rather than refused.

**Example:**
```python
# WRONG — the provider adds a "sid" claim one morning, and every token is rejected
def read_portal_claims(claims: Mapping[str, object]) -> PortalClaims:
    unexpected = claims.keys() - _READ_CLAIMS
    if unexpected:
        raise RejectedCredentialsError(f"unexpected claims: {sorted(unexpected)}")
    return PortalClaims(
        subject=_claim_text(claims, "sub"), scope=_claim_text(claims, "scope", default="")
    )

# CORRECT — the claims this service reads are validated; the provider's additions pass by
def read_portal_claims(claims: Mapping[str, object]) -> PortalClaims:
    return PortalClaims(
        subject=_claim_text(claims, "sub"), scope=_claim_text(claims, "scope", default="")
    )
```

## Authorization

### Whether this caller may touch this resource is checked in the service — next to the load for one, in the query for a list

**Why:** the edge establishes who is calling, once for every route, with the public routes as the
reviewed exception; it has not loaded the resource, so it cannot know whether the caller may touch
it. A route guarded by "is logged in" or by a role lets every pupil read every submission whose id
they can guess or enumerate — IDOR, the most common access-control flaw. Opaque ids make guessing
harder; they do not make the check optional. Where the resource's existence is itself the secret,
someone else's submission is answered exactly like a missing one; a 403 would confirm the id is
real. A list filtered after the query lets pagination, counts and totals see rows the caller may
not — page one holds three submissions of fifty, and the total gives away the rest — so the
repository takes the pupil.

**Example:**
```python
# WRONG — any signed-in caller who knows an id gets the submission
def _readable_submission(
    caller: PortalCaller, submission: HomeworkSubmission | None, submission_id: SubmissionId
) -> HomeworkSubmission:
    if submission is None:
        raise SubmissionNotFoundError(submission_id)
    return submission

# CORRECT — someone else's submission is answered exactly like a missing one
def _readable_submission(
    caller: PortalCaller, submission: HomeworkSubmission | None, submission_id: SubmissionId
) -> HomeworkSubmission:
    if submission is None or not _can_read_submission(caller, submission):
        raise SubmissionNotFoundError(submission_id)
    return submission

def _can_read_submission(caller: PortalCaller, submission: HomeworkSubmission) -> bool:
    return submission.pupil_id == caller.person_id or _MARK_SUBMISSIONS_SCOPE in caller.scopes
```

### A caller who may see a resource but not act on it gets a permission error

**Why:** not found or forbidden is chosen per resource. Where a teacher may read a submission but
not withdraw it, its existence is no secret, and the service raises a permission error the edge
maps to 403. A scope or a role is the coarse gate the edge may check first; ownership is the fine
one the service always checks.

**Example:**
```python
# WRONG — anyone who can read the submission can withdraw it
@final
class SubmissionDesk:
    def __init__(self, *, submissions: SubmissionStore) -> None:
        self._submissions = submissions

    async def withdraw(self, caller: PortalCaller, submission_id: SubmissionId) -> None:
        found = await self._submissions.find(submission_id)
        submission = _readable_submission(caller, found, submission_id)
        await self._submissions.remove(submission.submission_id)

# CORRECT — reading and withdrawing are different permissions
@final
class SubmissionDesk:
    def __init__(self, *, submissions: SubmissionStore) -> None:
        self._submissions = submissions

    async def withdraw(self, caller: PortalCaller, submission_id: SubmissionId) -> None:
        found = await self._submissions.find(submission_id)
        submission = _readable_submission(caller, found, submission_id)
        if submission.pupil_id != caller.person_id:
            raise SubmissionPermissionError(submission_id, action="withdraw")
        await self._submissions.remove(submission.submission_id)
```

## Rejections

### No valid credentials is 401, a valid caller refused is 403, unreachable signing keys are 503

**Why:** 401 carries `WWW-Authenticate: Bearer` and tells a client to authenticate again; 403 says
the credentials are fine and the action is not. A key set that cannot be fetched answered as 401
makes every client drop its session against an outage, and the alert says "pupils failing to sign
in". Every rejected token gets the same body: "Signature has expired" against "Invalid audience"
tells someone probing with a stolen token which checks passed. The reason goes to the server's
records — the chained cause, and a counter with a `reason` attribute — at `INFO` at most, since a
rejected token is an expected client mistake.

### A token travels in a header, and the access log records an allowlist of headers

**Why:** a query string lands in proxy logs and browser history; a denylist with `Authorization`
and `Cookie` struck out misses the next header that carries a credential. A span's attributes are
a log too, and the caller's id goes there, never the claims (`logging.md`).

### A session cookie is `Secure`, `HttpOnly`, `SameSite` and `__Host-`-prefixed

**Why:** a browser session is an opaque id from `secrets.token_urlsafe`, not a JWT. Without
`Secure` it travels over plain HTTP; without `HttpOnly` any script on the page reads it; `SameSite`
withholds it from cross-site subrequests, though it does not replace CSRF protection for
state-changing requests. The `__Host-` prefix makes the browser refuse the cookie unless it is
`Secure`, has `Path=/` and no `Domain`. Frameworks default to none of this.

## Issuing Tokens and Guarding Credentials

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

### A signing key rotates through the key set: publish, wait the cache lifetime, sign, retire

**Why:** verifiers cache the key set; a key used to sign before they fetched it fails every token
until their caches expire. The old key stays published until its last token has expired.

### A credential endpoint counts attempts per account and per source, in the shared cache

**Why:** a sign-in, reset or token endpoint is guessed against; a counter in the process is one per
worker and starts afresh on every restart — four workers grant four times the attempts. The counter
lives in the shared cache with the window as its TTL.

## Service-to-Service Credentials

### Each service has its own credential, and the token names the service it is for

**Why:** one static key shared by every caller cannot be rotated without a coordinated deploy or
revoked for one caller alone; a client-credentials token, a workload identity or mutual TLS is per
service. The token's `aud` names the receiving service, which verifies it like any other — a token
minted for one service and replayed against another is rejected. A user's token is not forwarded
across a trust boundary: inside one, the next service verifies it with its own audience in the
list or exchanges it; across one, the call uses the service's own credential. The client secret
comes from the environment or a secret manager.

### An outbound token is fetched once and reused until shortly before its `exp`

**Why:** fetched per request, every call pays a round trip to the identity provider and its rate
limit; cached past its `exp`, every call fails. The client object the root owns keeps it, and
renews a safety margin before expiry.

## Testing

### A fake verifier issues opaque tokens and can lose its signing keys, and every implementation hands the one contract suite a harness that does both

**Why:** a real verifier needs keys, a clock and a key set server; a fake that accepts every token
lets no test reach a rejection. The fake maps the tokens it issued back to their callers and stops
answering when its keys are cut off, so both failures of the contract are reachable from a unit
test. Issuing a token and cutting off the keys differ per implementation — a dict for the fake, a
generated key and a local key set server for a JWT verifier — so each fixture hands the tests a
harness with both, and the tests are written once. A third contract test sends a token nobody
issued and expects `RejectedCredentialsError`; rejections only one implementation can produce — an
expired JWT, `alg` `none` — are that implementation's own tests.

**Example:**
```python
# WRONG — the fake is tested by nothing, and the JWT verifier by its own separate tests
def test_in_memory_verifier_accepts_issued_token() -> None:
    verifier = InMemoryAccessTokenVerifier()
    token = verifier.issue(pupil_caller())

    verified = verifier.verify(token)

    assert verified == pupil_caller()

# CORRECT — one suite, parametrized over every implementation's harness
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class AccessTokenVerifierHarness:
    verifier: AccessTokenVerifier
    issue: Callable[[PortalCaller], str]
    cut_off_signing_keys: Callable[[], None]

@pytest.fixture(
    params=[
        pytest.param("in_memory", id="in_memory"),
        pytest.param("jwt", id="jwt", marks=pytest.mark.integration),
    ]
)
def verifier_harness(request: pytest.FixtureRequest) -> AccessTokenVerifierHarness:
    harness: AccessTokenVerifierHarness = request.getfixturevalue(
        f"{request.param}_verifier_harness"
    )
    return harness

def test_verify_reports_unreachable_signing_keys(
    verifier_harness: AccessTokenVerifierHarness,
) -> None:
    token = verifier_harness.issue(pupil_caller())
    verifier_harness.cut_off_signing_keys()

    with pytest.raises(SigningKeysUnreachableError, match="could not be fetched"):
        verifier_harness.verifier.verify(token)
```

### Authorization is tested at the service, with the owner and another pupil

**Why:** the test with a caller who does not own the resource is the one that catches IDOR; a test
with only the owner passes a service that checks nothing.

**Example:**
```python
# WRONG — only the owner asks, so a missing ownership check passes
async def test_open_returns_submission_to_its_pupil(desk: SubmissionDesk) -> None:
    submission = await desk.open(_PUPIL, _SUBMISSION_ID)

    assert submission.submission_id == _SUBMISSION_ID

# CORRECT — another pupil is answered exactly like a missing submission
async def test_open_hides_submission_from_another_pupil(desk: SubmissionDesk) -> None:
    with pytest.raises(SubmissionNotFoundError):
        await desk.open(_OTHER_PUPIL, _SUBMISSION_ID)
```

