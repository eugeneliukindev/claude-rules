---
name: python-tenacity
description: >-
  tenacity mechanics for retry policies: retry keyed on a translated exception, a stop with a time
  budget, proportional jitter, logging, testing a policy. Use when code imports tenacity or
  applies @retry.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# tenacity

Checked against tenacity 9.2. What is retried — only a transient failure, at one level, within a
total deadline — is `python-boundaries`; inside a worker, a backoff that fits the handler's deadline
is tenacity's and a longer wait the broker's (`python-workers`); a gRPC call whose channel retries
through `retryPolicy` gets no tenacity around it (`python-grpc`). This file is how the policy is
written once that is decided.

### A policy names `retry=` by exception type, `stop=` with a total budget, and `reraise=True`

**Why:** without `retry=` every exception is retried, a `KeyError` from your own parsing included;
keyed on the adapter's translated transient type, the policy reads as a sentence. Without `stop=`
it retries forever — a dependency's outage becomes an unkillable worker — and `stop_after_delay`,
checked between attempts, bounds the total while the per-request timeout bounds each one. Without
`reraise=True` the caller gets `RetryError` and loses the exception its handling was written for.

**Example:**
```python
# WRONG — the README shape: every exception retried, bugs included, the cause hidden in RetryError
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
async def fetch_rates(*, upstream: RatesUpstream) -> RateTable:
    return await upstream.fetch_table()


# CORRECT — transient failures only, a total budget, and the real exception on give-up
@retry(
    retry=retry_if_exception_type(TransientUpstreamError),
    wait=wait_exponential_jitter(multiplier=0.2, max=5.0, jitter=0.2),
    stop=stop_after_attempt(3) | stop_after_delay(_FETCH_BUDGET_SECONDS),
    reraise=True,
)
async def fetch_rates(*, upstream: RatesUpstream) -> RateTable:
    return await upstream.fetch_table()
```

### The jitter is stated in proportion to the backoff, and the first wait is `multiplier=`

**Why:** `wait_exponential_jitter` defaults to `jitter=1`, in seconds; with `multiplier=0.2` that
random second is five times the wait it perturbs, and the exponential curve stops mattering.
`initial=` is the deprecated name of `multiplier=` since 9.2 and warns when the policy is built — at
import, for a module-level one — which a suite with warnings as errors turns into a failure.

**Example:**
```python
# WRONG — jitter left at 1 second, five times the 0.2-second first wait, and a deprecated name
_FETCH_WAIT: Final = wait_exponential_jitter(initial=0.2, max=5.0)


# CORRECT — the first wait and the jitter both chosen
_FETCH_WAIT: Final = wait_exponential_jitter(multiplier=0.2, max=5.0, jitter=0.2)
```

### A retried call is logged before each sleep, and the give-up once, at the boundary

**Why:** a silent retry hides a degrading dependency until it fails completely;
`before_sleep_log` makes each retry visible. The final failure is logged once, where it is
converted, never on every attempt.

**Example:**
```python
# WRONG — retries happen in silence
_RATES_POLICY: Final = retry(
    retry=retry_if_exception_type(TransientUpstreamError),
    wait=_FETCH_WAIT,
    stop=stop_after_attempt(3),
    reraise=True,
)


# CORRECT — every retry leaves a warning that names the call and the wait
_RATES_POLICY: Final = retry(
    retry=retry_if_exception_type(TransientUpstreamError),
    wait=_FETCH_WAIT,
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
async def test_fetch_rates_retries_transient_failures() -> None:
    upstream = FlakyRatesUpstream(failures=_FAILURES_BEFORE_SUCCESS)

    await fetch_rates(upstream=upstream)

    assert upstream.calls == _FAILURES_BEFORE_SUCCESS + 1


# CORRECT — the same policy without the waits; attempts and classification stay under test
async def test_fetch_rates_retries_transient_failures() -> None:
    upstream = FlakyRatesUpstream(failures=_FAILURES_BEFORE_SUCCESS)

    await fetch_rates.retry_with(wait=wait_none())(upstream=upstream)

    assert upstream.calls == _FAILURES_BEFORE_SUCCESS + 1
```
