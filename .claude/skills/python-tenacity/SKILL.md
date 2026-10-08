---
name: python-tenacity
description: >-
  tenacity retry policies: keying retry= on a translated exception type rather than a status code,
  always setting stop= with a total time budget and reraise=True, choosing jitter in proportion to
  the backoff instead of the one-second default, before_sleep_log for visibility, and testing a
  policy through copy(wait=wait_none()). Use when Python code imports tenacity or applies the
  @retry decorator.
---

# tenacity

Checked against tenacity 9.1. Where retries belong, what may be retried and how budgets nest is
in `python-boundaries`; this skill is how to write the policy once that is decided.

## The Shape of a Retry Policy

Four decisions, all explicit, none left to a default:

```python
# WRONG — the README shape: retries every exception, bugs included, and hides the cause in
# RetryError
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
async def _fetch_page(session: AsyncSession, url: str) -> Page: ...

# CORRECT
@retry(
    retry=retry_if_exception_type(TransientUpstreamError),
    wait=wait_exponential_jitter(initial=0.2, max=5.0, jitter=0.2),
    stop=stop_after_attempt(3) | stop_after_delay(_FETCH_BUDGET_SECONDS),
    reraise=True,
)
async def _fetch_page(session: AsyncSession, url: str) -> Page: ...
```

- **`retry=` keys on an exception type, never on a status code.** Translate the upstream failure
  into a transient and a permanent error first, in the adapter; then the policy reads as a sentence
  and the classification lives in one place instead of being spread across every call site. Without
  `retry=` the default retries every exception — a `KeyError` from your own parsing three times.
- **`stop=` is always set.** Without it the default retries forever, which turns a dependency's
  outage into an unkillable worker. Combine the attempt count with a total budget:
  `stop_after_delay` is checked between attempts, so the per-request timeout still bounds each one.
- **`reraise=True`, always.** Without it tenacity raises `RetryError`, and the caller loses the
  actual exception — including the one your error handling upstream was written to catch.

## Set the Jitter Explicitly

`wait_exponential_jitter` defaults to `jitter=1`, measured in seconds. With `initial=0.2` that
random second is five times the backoff it is supposed to perturb: the exponential curve stops
mattering and every wait is dominated by noise. State the jitter in proportion to the backoff.

```python
# WRONG — jitter left at its default of 1 second, five times the 0.2-second first wait
_FETCH_WAIT: Final = wait_exponential_jitter(initial=0.2, max=5.0)

# CORRECT — the jitter stated in proportion to the backoff it perturbs
_FETCH_WAIT: Final = wait_exponential_jitter(initial=0.2, max=5.0, jitter=0.2)
```

The same care applies to `wait_exponential`'s `multiplier` and `max` — a policy whose numbers were
never chosen is a policy nobody can reason about during an incident.

## What Not to Retry

Business rejections, non-idempotent writes without a key, and a second level of retries — the rules
and their carve-out are in `python-boundaries`.

## Observability

- **`before_sleep=before_sleep_log(logger, logging.WARNING)`** so a retried call is visible. A
  silent retry hides a degrading dependency until it fails completely.
- Log the give-up once, at the boundary that converts the failure — not on every attempt.

## Testing a Policy

- **Test a copy of the policy with `wait=wait_none()`** — the attempt count and the exception
  classification stay under test, which is what matters, and the suite does not sleep through the
  backoff. `fn.retry_with(wait=wait_none())` does this at runtime, but the decorator is typed as
  returning the original callable, so `mypy --strict` reports `attr-defined`. The typed route is a
  policy object: `_RETRY_POLICY = Retrying(...)` in the adapter,
  `_RETRY_POLICY.copy(wait=wait_none())` in the test, called as `policy(fetch_rates)`.
- Assert the number of attempts against a fake that counts calls, not against timing.
