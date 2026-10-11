# Testing Authentication and Authorization

## Contents

- A fake verifier for the unit tests
- One contract suite, a harness per implementation
- Authorization tested at the service, with a stranger

The JWT implementation's harness — a generated key and a local key set server — is in
`python-pyjwt`; testing the edge through the app is in `python-fastapi`.

### The unit tests take a fake verifier that issues opaque tokens and can lose its key set

**Why:** a real verifier needs keys, a clock and a key set server; the fake maps the tokens it
issued back to their principals, and stops answering when its key set is taken offline, so both
failures of the contract are reachable from a unit test.

**Example:**
```python
# WRONG — every token is accepted, so no test ever reaches a rejection
@final
class InMemoryTokenVerifier(TokenVerifier):
    def __init__(self, *, principal: Principal) -> None:
        self._principal = principal

    @override
    def verify(self, token: str) -> Principal:
        return self._principal


# CORRECT — tokens are issued and checked, and the key set can go away
@final
class InMemoryTokenVerifier(TokenVerifier):
    def __init__(self) -> None:
        self._principal_by_token: dict[str, Principal] = {}
        self.is_key_set_reachable = True

    def issue(self, principal: Principal) -> str:
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        self._principal_by_token[token] = principal
        return token

    @override
    def verify(self, token: str) -> Principal:
        if not self.is_key_set_reachable:
            raise KeySetUnavailableError(_KEY_SET_URL)
        principal = self._principal_by_token.get(token)
        if principal is None:
            raise InvalidCredentialsError("unknown token")
        return principal
```

### The fake and every real verifier pass one contract suite, through a harness per implementation

**Why:** issuing a token and taking the key set offline differ per implementation, so each fixture
hands the tests a harness with both, and the tests are written once (`python-contracts`). A third
contract test sends a token nobody issued and expects `InvalidCredentialsError`; rejections only one
implementation can produce — an expired JWT, `alg` `none` — are that implementation's own tests.

**Example:**
```python
# WRONG — the fake is tested by nothing, and the JWT verifier by its own separate tests
def test_in_memory_verifier_accepts_issued_token() -> None:
    verifier = InMemoryTokenVerifier()
    token = verifier.issue(make_principal())

    verified = verifier.verify(token)

    assert verified == make_principal()


# CORRECT — one suite, parametrized over every implementation's harness
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class TokenVerifierHarness:
    verifier: TokenVerifier
    issue_token: Callable[[Principal], str]
    take_key_set_offline: Callable[[], None]


@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("jwt", id="jwt", marks=pytest.mark.integration),
    ]
)
def token_verifier_harness(request: pytest.FixtureRequest) -> TokenVerifierHarness:
    harness: TokenVerifierHarness = request.getfixturevalue(
        f"{request.param}_token_verifier_harness"
    )
    return harness


def test_verify_reports_unreachable_key_set_as_unavailable(
    token_verifier_harness: TokenVerifierHarness,
) -> None:
    token = token_verifier_harness.issue_token(make_principal())
    token_verifier_harness.take_key_set_offline()

    with pytest.raises(KeySetUnavailableError, match="could not be fetched"):
        token_verifier_harness.verifier.verify(token)
```

### Authorization is tested at the service, with an owner and a stranger

**Why:** the test with a principal that does not own the resource is the one that catches IDOR; a
test with only the owner passes a service that checks nothing.

**Example:**
```python
# WRONG — only the owner asks, so a missing ownership check passes
async def test_open_returns_document_to_its_owner(access: DocumentAccess) -> None:
    document = await access.open(_OWNER, _DOCUMENT_ID)

    assert document.document_id == _DOCUMENT_ID


# CORRECT — a stranger is answered exactly like a missing document
async def test_open_hides_document_from_stranger(access: DocumentAccess) -> None:
    with pytest.raises(DocumentNotFoundError):
        await access.open(_STRANGER, _DOCUMENT_ID)
```
