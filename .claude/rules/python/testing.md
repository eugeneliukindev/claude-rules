---
paths:
  - "**/tests/**/*.py"
  - "**/test_*.py"
  - "**/conftest.py"
  - "**/testing/**/*.py"
  - "**/fakes.py"
---

# Testing

Supplement to the other Python rules, for writing and reviewing tests. `pytest` is the framework;
its mechanics — async tests, property tests, HTTP and container fixtures, coverage — are in
`python-pytest`.

## Levels

Most tests are unit, fewer integration, and only critical user flows e2e — the pyramid keeps the
suite fast enough to run on every change. A test belongs to one level; how the levels are kept apart
— directory, marker, naming — is a project decision, that they are is not.

- **Unit** — one function or class in isolation, collaborators replaced by in-memory fakes. Fast
  enough that nobody thinks about running them. Every new function and class gets them.
- **Integration** — components against real infrastructure: database, broker, cache. The
  infrastructure is real here; a mocked database only proves the mock works.
- **E2e** — complete user-facing flows against a running system, critical paths only.

## Fakes, Not Mocks

- **Every contract (`UserRepository`, `Notifier`) has an in-memory fake in the tests** —
  `tests/fakes.py`, inheriting the contract like any implementation — injected in unit tests, and
  held to the same contract suite as the real ones (`python-contracts`). A fake exercises the
  contract; a `MagicMock` records calls and happily accepts methods that do not exist.
- **Mock only at a process boundary you do not own** — the network, the broker; never the clock,
  which is injected and replaced by a fixed one. Then use the `mocker` fixture (or
  `unittest.mock.patch` as a context manager) and always `spec=` the real class, so a nonexistent
  attribute fails.
- **Patching your own module is a design signal**: `patch("app.registration._send_welcome")` means
  the dependency should have been injected. Fix the constructor rather than patch. Patching stays
  legitimate for boundaries that cannot be injected — stdlib internals, third-party module state.
- **Assert outcomes, not conversations.** Check the state of the fake or the return value;
  `assert_called_once_with` chains mirror the implementation line by line, break on every refactor
  and catch nothing.

```python
# WRONG — patches our own module and asserts the conversation
def test_register_user_sends_welcome(mocker: MockerFixture) -> None:
    send_welcome = mocker.patch("app.registration._send_welcome")
    register_user("ann@example.com")
    send_welcome.assert_called_once_with("ann@example.com")

# CORRECT — the dependency is injected as a fake, and the outcome is asserted
def test_register_user_sends_welcome_to_new_user() -> None:
    notifier = InMemoryNotifier()

    register_user(notifier, "ann@example.com")

    assert notifier.sent == [Welcome(recipient="ann@example.com")]
```

## Structure

- **Arrange, act, assert** in every test, the three phases separated by a blank line and never
  merged — the reader finds the action under test without reading the setup.
- **Several input/output combinations are one `@pytest.mark.parametrize`** with a `pytest.param`
  per case, each with an `id` describing the scenario in plain words — the id is what a failing
  run prints. A table of scalars alone may leave the ids to pytest, which prints the values.

```python
@pytest.mark.parametrize(
    ("prices", "tax_rate", "expected_total"),
    [
        pytest.param(
            [Decimal("100.00"), Decimal("50.00")],
            Decimal("0.10"),
            Decimal("165.00"),
            id="two_items_ten_percent_tax",
        ),
        pytest.param([Decimal("200.00")], Decimal("0"), Decimal("200.00"), id="single_item_no_tax"),
        pytest.param([], Decimal("0.10"), Decimal("0"), id="empty_cart_returns_zero"),
    ],
)
def test_total_includes_tax(
    prices: list[Decimal], tax_rate: Decimal, expected_total: Decimal
) -> None:
    total = calculate_total(prices, tax_rate)

    assert total == expected_total
```

- **A test you write is a file in the suite.** Run it from its own file rather than inline, and
  keep it afterwards — a test that ran once and was deleted proved nothing to the next change. The
  folder the tests write their outputs to is in `.gitignore`.

## Naming and Data

- **Test names are specifications**: `test_<unit>_<scenario>_<expected>` or behaviour phrasing —
  `test_allow_rejects_request_when_bucket_is_empty`. Never `test_1`, `test_happy_path`, or a name
  that only repeats the function name.
- **One behaviour per test.** Several asserts are fine when they verify facets of the same outcome;
  two unrelated behaviours are two tests.
- **`pytest.raises` takes `match=`**, a distinctive fragment of the message, **or the test compares
  the whole structured payload** the error carries (`excinfo.value.errors() == [...]`); a bare
  `pytest.raises(ValueError)` passes on the wrong `ValueError`. The carried data is asserted too:
  `with pytest.raises(OrderNotFoundError, match="order 42") as excinfo: ...` then
  `assert excinfo.value.order_id == OrderId(42)`.
- **Fixtures are factories, not constants**: a valid default the test overrides in one place, not a
  shared object a dozen tests silently depend on. Shared fixtures live in the nearest `conftest.py`;
  a fixture one module uses lives in that module.
  ```python
  # WRONG — one shared order: the test that needs it paid changes it for every other test
  @pytest.fixture
  def order() -> Order: ...
  # CORRECT — each test builds the order it needs and states only what matters to it
  def make_order(*, status: OrderStatus = OrderStatus.NEW) -> Order: ...
  ```
- **Test data says only what matters**: values relevant to the behaviour are explicit in the test,
  everything else comes from the factory defaults. A magic value outside a parametrize table gets
  the same named-constant treatment as production code.
- **Determinism is enforced**: time comes from the injected clock (`time-machine` only for code you
  do not own that reads the clock itself), randomness is seeded, `pytest-randomly` surfaces hidden
  ordering dependencies, and waiting polls with a timeout instead of `sleep()`.
- Unit tests may use pytest's sandboxes such as `tmp_path`; they never touch the network, real
  time, or global state.
- **Warnings are errors in the suite** (`filterwarnings = ["error"]`): a deprecation fails the day
  it appears. A test that expects one asserts it — `pytest.warns(DeprecationWarning, match=...)` —
  and tests of a deprecated path sit together, so removing the path deletes them in one place.
