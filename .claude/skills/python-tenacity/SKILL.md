---
name: python-tenacity
description: >-
  tenacity mechanics for retry policies: retry keyed on a translated exception, a stop with a time
  budget, proportional jitter, logging, testing a policy. Use when code imports tenacity or
  applies @retry. Not for when to retry (python-boundaries).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# tenacity

Checked against tenacity 9.2. Which failures are retried, at which level and under which deadline
is `python-boundaries`; this skill is how tenacity spells the policy.

### A policy names `retry=` by exception type, `stop=` with a total budget, and `reraise=True`

**Why:** without `retry=` every exception is retried, a `KeyError` from your own parsing included;
`retry_if_exception_type` keyed on the adapter's transient type retries that alone. Without `stop=`
it retries forever — a dependency's outage becomes an unkillable worker — and `stop_after_delay`,
checked between attempts, bounds the total while the per-request timeout bounds each one. Without
`reraise=True` the caller gets `RetryError` and loses the exception its handling was written for.

**Example:**
```python
# WRONG — the README shape: every exception retried, bugs included, the cause hidden in RetryError
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
async def lookup_postal_code(
    postal_code: PostalCode, *, directory: AddressDirectory
) -> AddressMatch:
    return await directory.find_addresses(postal_code)


# CORRECT — transient failures only, a total budget, and the real exception on give-up
@retry(
    retry=retry_if_exception_type(TransientDirectoryError),
    wait=wait_exponential_jitter(multiplier=0.2, max=5.0, jitter=0.2),
    stop=stop_after_attempt(3) | stop_after_delay(_LOOKUP_BUDGET_SECONDS),
    reraise=True,
)
async def lookup_postal_code(
    postal_code: PostalCode, *, directory: AddressDirectory
) -> AddressMatch:
    return await directory.find_addresses(postal_code)
```

### The jitter is stated in proportion to the backoff, and the first wait is `multiplier=`

**Why:** `wait_exponential_jitter` defaults to `jitter=1`, in seconds; with `multiplier=0.2` that
random second is five times the wait it perturbs, and the exponential curve stops mattering.
`initial=` is the deprecated name of `multiplier=` since 9.2 and warns when the policy is built — at
import, for a module-level one — which a suite with warnings as errors turns into a failure.

**Example:**
```python
# WRONG — jitter left at 1 second, five times the 0.2-second first wait, and a deprecated name
_LOOKUP_WAIT: Final = wait_exponential_jitter(initial=0.2, max=5.0)


# CORRECT — the first wait and the jitter both chosen
_LOOKUP_WAIT: Final = wait_exponential_jitter(multiplier=0.2, max=5.0, jitter=0.2)
```

### A retried call is logged before each sleep with `before_sleep_log`

**Why:** a silent retry hides a degrading dependency until it fails completely; `before_sleep_log`
writes one line per retry naming the call, the exception and the wait, and with `reraise=True` the
give-up reaches whoever handles the exception, which logs it.

**Example:**
```python
# WRONG — retries happen in silence
_LOOKUP_POLICY: Final = retry(
    retry=retry_if_exception_type(TransientDirectoryError),
    wait=_LOOKUP_WAIT,
    stop=stop_after_attempt(3),
    reraise=True,
)


# CORRECT — every retry leaves a warning that names the call and the wait
_LOOKUP_POLICY: Final = retry(
    retry=retry_if_exception_type(TransientDirectoryError),
    wait=_LOOKUP_WAIT,
    stop=stop_after_attempt(3),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
```

### A policy is tested through `retry_with(wait=wait_none())`, counting calls on a fake

**Why:** the attempt count and the exception classification stay under test, which is what
matters, and the suite does not sleep through the backoff. Since 9.2 `retry_with` is typed, so the
test calls the public function it already tests and reaches into nothing private. Attempts are
asserted on a fake that counts calls, never on timing.

**Example:**
```python
# WRONG — the test sleeps through the real backoff on every run
async def test_lookup_postal_code_retries_transient_failures() -> None:
    directory = FlakyAddressDirectory(failures=_FAILURES_BEFORE_ANSWER)

    await lookup_postal_code(_POSTAL_CODE, directory=directory)

    assert directory.calls == _FAILURES_BEFORE_ANSWER + 1


# CORRECT — the same policy without the waits; attempts and classification stay under test
async def test_lookup_postal_code_retries_transient_failures() -> None:
    directory = FlakyAddressDirectory(failures=_FAILURES_BEFORE_ANSWER)

    await lookup_postal_code.retry_with(wait=wait_none())(_POSTAL_CODE, directory=directory)

    assert directory.calls == _FAILURES_BEFORE_ANSWER + 1
```
