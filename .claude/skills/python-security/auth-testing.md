# Testing Authentication and Authorization

## Contents

- A fake verifier, and one contract suite with a harness per implementation
- Authorization tested at the service, with another pupil

A verifier's fake is held to the contract suite like any other; what follows is what that suite
needs on top.

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
