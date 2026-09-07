# tenacity

Not loaded automatically — open it when the code imports `tenacity`.

Retries belong in the adapter that talks to the outside world. A service sees one call that either
succeeded or raised a final error; it never contains a retry loop.

## The Shape of a Retry Policy

Four decisions, all explicit, none left to a default:

```python
@retry(
    retry=retry_if_exception_type(TransientUpstreamError),
    wait=wait_exponential_jitter(initial=0.2, max=5.0, jitter=0.2),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _fetch_page(session: Session, url: str) -> Page: ...
```

- **`retry=` keys on an exception type, never on a status code.** Translate the upstream failure into
  a transient and a permanent error first, in the adapter; then the policy reads as a sentence and
  the classification lives in one place instead of being spread across every call site.
- **`stop=` is always set.** Without it the default retries forever, which turns a dependency's
  outage into an unkillable worker.
- **`reraise=True`, always.** Without it tenacity raises `RetryError`, and the caller loses the
  actual exception — including the one your error handling upstream was written to catch.

## Set the Jitter Explicitly

`wait_exponential_jitter` defaults to `jitter=1`, measured in seconds. With `initial=0.2` that
random second is five times the backoff it is supposed to perturb: the exponential curve stops
mattering and every wait is dominated by noise. State the jitter in proportion to the backoff.

The same care applies to `wait_exponential`'s `multiplier` and `max` — a policy whose numbers were
never chosen is a policy nobody can reason about during an incident.

## What Not to Retry

- **Never a business rejection.** Validation failures, conflicts, auth errors: retrying a `409` is a
  loop, not resilience.
- **Never a non-idempotent write** without an idempotency key, or a natural key and an upsert on your
  side. Three attempts at a create is three rows.
- **Never at two levels.** Retries nest multiplicatively — four attempts inside a caller that also
  makes four is sixteen, and a five-second budget becomes eighty. Retry in the adapter only, and let
  the outermost boundary own the total deadline.

## Observability

- **`before_sleep=before_sleep_log(logger, logging.WARNING)`** so a retried call is visible. A silent
  retry hides a degrading dependency until it fails completely.
- Log the give-up once, at the boundary that converts the failure — not on every attempt.

## Testing a Policy

- **`retry_with(...)` returns a reconfigured copy** — override the wait with `wait_none()` in tests
  to exercise the policy without sleeping through it. That keeps the attempt count and the exception
  classification under test, which is what matters, and keeps the suite fast.
- Assert the number of attempts against a fake that counts calls, not against timing.
