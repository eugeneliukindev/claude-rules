# Testing Authentication and Authorization

## Contents

- A fake verifier for the unit tests
- One contract suite, a harness per implementation
- Authorization tested at the service, with another pupil

A verifier's fake is held to the contract suite like any other; what follows is what that suite
needs on top.

### The unit tests take a fake verifier that issues opaque tokens and can lose its signing keys

**Why:** a real verifier needs keys, a clock and a key set server; the fake maps the tokens it
issued back to their callers, and stops answering when its keys are cut off, so both failures of
the contract are reachable from a unit test.

**Example:**
```python
# WRONG — every token is accepted, so no test ever reaches a rejection
@final
class InMemoryAccessTokenVerifier(AccessTokenVerifier):
    def __init__(self, *, caller: PortalCaller) -> None:
        self._caller = caller

    @override
    def verify(self, token: str) -> PortalCaller:
        return self._caller


# CORRECT — tokens are issued and checked, and the signing keys can go away
@final
class InMemoryAccessTokenVerifier(AccessTokenVerifier):
    def __init__(self) -> None:
        self._caller_by_token: dict[str, PortalCaller] = {}
        self.are_signing_keys_reachable = True

    def issue(self, caller: PortalCaller) -> str:
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        self._caller_by_token[token] = caller
        return token

    @override
    def verify(self, token: str) -> PortalCaller:
        if not self.are_signing_keys_reachable:
            raise SigningKeysUnreachableError(_KEY_SET_URL)
        caller = self._caller_by_token.get(token)
        if caller is None:
            raise RejectedCredentialsError("unknown token")
        return caller
```

### Each implementation hands the contract suite a harness that issues a token and cuts off its keys

**Why:** issuing a token and making the signing keys unreachable differ per implementation — a dict
for the fake, a generated key and a local key set server for a JWT verifier — so each fixture hands
the tests a harness with both, and the tests are written once. A third contract test sends a token
nobody issued and expects `RejectedCredentialsError`; rejections only one implementation can
produce — an expired JWT, `alg` `none` — are that implementation's own tests.

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
