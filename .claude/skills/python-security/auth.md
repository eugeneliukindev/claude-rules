# Authentication and Authorization

How a token becomes an identity, and where that identity is checked, whatever the token library.

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
