---
paths:
  - "**/tests/**/*.py"
  - "**/test_*.py"
  - "**/conftest.py"
  - "**/testing/**/*.py"
  - "**/fakes.py"
---

# Testing

Supplement to `core.md`. Governs tests, both writing and reviewing them.

## Testing

**MUST** follow the testing pyramid: the majority of tests are unit tests, fewer are integration
tests, and only critical user flows have e2e tests.

Three levels, and a test belongs to exactly one of them. Where they are kept and how that is
signalled — by directory, by marker, by naming — is a project decision; that the three exist and
stay separated is not.

- **Unit** — one function or class in isolation, collaborators replaced by in-memory fakes. Fast
  enough that nobody thinks about running them.
- **Integration** — components against real infrastructure: database, broker, cache. Do **NOT** mock
  infrastructure here; a mocked database only proves the mock works.
- **E2e** — complete user-facing flows against a running system. Keep them minimal: critical paths
  only.
- **MUST** write unit tests for all new functions and classes
- **MUST** use `pytest` as the testing framework
- **Prefer fakes over mocks.** For every interface (`BaseUserRepository`, `BaseNotifier`) keep an in-memory fake (`InMemoryUserRepository`) next to the real implementations and inject it in unit tests. Fakes exercise the contract; `MagicMock` only records calls and happily accepts methods that don't exist.
- **Mock only at the process boundary you don't own** — the network, the clock, the broker. When a `MagicMock` is genuinely needed, use the `mocker` fixture (`pytest-mock`) — or `unittest.mock.patch` as a context manager where `mocker` is unavailable — and always `spec=` the real class so nonexistent attributes fail.
- **`patch` targets are a design smell-meter**: patching your *own* internal modules (`patch("app.services.registration._send_welcome")`) means the dependency should have been injected. Fix the constructor, don't patch. Patching is legitimate only for boundaries that cannot be injected (stdlib internals in rare cases, third-party module state).
- **Assert outcomes, not conversations.** Check the state of the fake (`assert repository.saved == [user]`) or the return value; `assert_called_once_with` chains that mirror the implementation line-by-line break on every refactor while catching nothing.

- **NEVER** run tests you generate without first saving them as their own discrete file
- **NEVER** delete files created as a part of testing.
- Ensure the folder used for test outputs is present in `.gitignore`
- **MUST** follow the **Arrange-Act-Assert (AAA)** pattern in every test. Separate the three phases with a blank line. Never merge phases.
- **MUST** use `@pytest.mark.parametrize` with `pytest.param` for all tests that cover multiple input/output combinations. Each `pytest.param` **MUST** have an `id` that describes the scenario in plain English.

  ```python
  from decimal import Decimal

  import pytest

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
  def test_total_includes_tax(prices: list[Decimal], tax_rate: Decimal, expected_total: Decimal) -> None:
      total = calculate_total(prices, tax_rate)

      assert total == expected_total
  ```

### Test Naming and Structure

- **Test names are specifications**: `test_<unit>_<scenario>_<expected>` or behaviour phrasing — `test_allow_rejects_request_when_bucket_is_empty`, `test_expired_token_is_refreshed_before_use`. Never `test_1`, `test_happy_path`, `test_edge_case`, and never a name that just repeats the function name with no scenario.
- **One behaviour per test.** Several asserts are fine when they verify facets of the same outcome; asserting two unrelated behaviours means two tests.
- **`pytest.raises` always with `match=`** (a distinctive fragment of the message) and, when the exception carries data, assert the attributes via `excinfo.value`. A bare `pytest.raises(ValueError)` passes on the wrong `ValueError`.
- **Fixtures are factories, not constants**: `make_order(**overrides)` returning a valid default the test overrides in one place — not a shared `order` fixture that a dozen tests silently depend on. Shared fixtures live in the nearest `conftest.py`; a fixture used by one module lives in that module.
- **Determinism is enforced**: freeze time with the injected clock (or `time-machine` at boundaries); seed randomness; run with `pytest-randomly` so hidden ordering dependencies surface; no `sleep()`-based waiting — poll with a timeout or use fake timers.
- **Test data says only what matters**: values relevant to the behaviour are explicit in the test; everything else comes from the factory defaults. Magic values in a test need the same named-constant treatment as production code.
- Unit tests may touch pytest-provided sandboxes such as `tmp_path`; they never touch the network, real time, or global state.

### Coverage Policy

- Coverage is measured with **branch coverage on** (`--cov-branch`); line coverage alone hides untested `else` arms.
- **No single magic number.** The gate is layered: domain and services aim at ~100%; adapters and handlers are covered mainly by integration tests; generated code, migrations and `__main__` are excluded explicitly in config, not ignored silently.
- CI enforces a floor with `--cov-fail-under` and the floor only ratchets up.
- Coverage is a detector of untested code, **never** a target: a test that exists to color lines green (no meaningful assert) is worse than the gap it hides, because it converts an honest unknown into false confidence.
