---
paths:
  - "**/tests/**/*.py"
  - "**/test_*.py"
  - "**/conftest.py"
  - "**/testing/**/*.py"
  - "**/fakes.py"
---

# Testing

These add to the other Python rules, for writing and reviewing tests with `pytest`.

## Levels

- **Replace collaborators with fakes in a unit test, and use real infrastructure in an integration test.** Only the real thing exercises the constraint, the transaction and the SQL dialect a mocked database pretends to.
- **Write mostly unit tests, for every new function and class, fast enough that nobody thinks about running them.**
- **Keep each test in one level, and keep the levels apart by directory or marker.**
- **Keep every test you write as a file in the suite.** A check run once inline and deleted proves nothing to the next change.

## Structure

- **Write a test as Arrange-Act-Assert with one act, the phases separated by blank lines.** The call under test is then found at a glance; a second act is a second test.
- **Name a test for the behaviour: `test_<when>_<then>`, or `test_given_..._when_..._then_...` where the setup decides it.** A failing test then reads as the broken specification, where `test_renew` names a function.

## Fakes, Not Mocks

- **Give a contract a unit test depends on an in-memory fake, and assert the outcome.** A `MagicMock` accepts methods that do not exist, so a renamed method keeps every test green, and an `assert_called_once_with` chain breaks on every refactor; a contract only integration tests reach needs no fake until a unit test does.
- **Make the fake inherit the contract and pass its contract suite.**
- **Mock only a process boundary you do not own, against the real class.** Use `mocker.create_autospec(smtplib.SMTP, instance=True)` for a third-party class and inject the clock; needing to patch your own module means a missing constructor parameter.

## Assertions and Data

- **Write cases as one `parametrize`, each `pytest.param` with an `id`.** Copied tests drift apart, and the id is what a failing run prints; a table of scalars alone may leave the ids to pytest, which prints the values.
- **Pin an expected error or warning with `match=`, and assert the data it carries.** A bare `pytest.raises` passes on the wrong one, raised by the arrange step or for another subject.
- **Make warnings errors with `filterwarnings = ["error"]`, and assert a deprecated path with `pytest.warns(..., match=...)`.** A deprecation then fails the day it appears.
- **Arrange each test's data through the code's public functions.** A public function changes only with behaviour and validates on the way in.
- **Write through the library's API in a factory in `tests/factories.py` only where no public function reaches the state, the data is bulk or the test checks the stored row.** A helper the test does not check, like a `session_add()` wrapper, breaks it for its own reasons.
- **Share no seeded data, and build only what the test asserts on.** A class-wide seed couples every test to every row; reference data no test writes may be seeded once per session.

## Determinism

- **Fix time, randomness and order in the test.** Take time from the injected clock, with `time-machine` only for code you do not own that reads the clock itself, and seed randomness; a test that reads the real clock or sleeps is slow, and flaky on a loaded runner.
- **Poll with a timeout instead of `sleep()`.**
- **Keep unit tests off the network, real time and global state.**
