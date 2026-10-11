# Fakes and the Contract Suite

How a contract is declared and what its methods look like are in `SKILL.md`.

### A test fake is an implementation, and it lives with the tests

**Why:** `tests/fakes.py` inherits the contract like any other implementation, so a renamed method
breaks the fake too; the group that ships carries no test code.

**Example:**
```python
# WRONG — the fake ships with the package, and does not inherit the contract
# notifications/fake.py
class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, recipient: UserId, message: Message) -> None:
        self.sent.append(message)


# CORRECT — tests/fakes.py, inheriting the contract
@final
class InMemoryNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[tuple[UserId, Message]] = []

    @override
    def send(self, recipient: UserId, message: Message) -> None:
        self.sent.append((recipient, message))
```

### Every implementation passes one contract suite — the fake included

**Why:** the tests are written once against the contract and run for each implementation through a
parametrized fixture; the real ones carry the integration marker, so the unit run still takes the
fake. A fake not held to the same tests drifts, and the unit tests then prove the fake.

**Example:**
```python
# WRONG — the fake is tested by nothing, and the real repository by its own separate tests
def test_in_memory_repository_finds_saved_document() -> None:
    repository = InMemoryDocumentRepository()
    document = make_document()
    repository.save(document)
    assert repository.find(document.document_id) == document


# CORRECT — one suite, every implementation
@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def document_repository(request: pytest.FixtureRequest) -> DocumentRepository:
    repository: DocumentRepository = request.getfixturevalue(f"{request.param}_document_repository")
    return repository


def test_saved_document_is_found_by_id(document_repository: DocumentRepository) -> None:
    document = make_document()

    document_repository.save(document)

    assert document_repository.find(document.document_id) == document
```
