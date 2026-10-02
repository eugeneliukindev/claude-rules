---
name: python-niquests
description: >-
  niquests HTTP client practice, which transfers to httpx almost unchanged: one session owned by
  the composition root instead of module-level calls, a timeout on every request, raise_for_status
  rather than assuming success, transport and status errors translated at the adapter, deliberate
  redirect handling, TLS verification left on, and where retries belong. Use when Python code
  imports niquests or httpx, builds a session, or makes an outbound HTTP request.
---

# niquests

Checked against niquests 3.21. The API is `requests`-shaped, so the habits below transfer to
`httpx` almost unchanged; what does not transfer is called out.

## One Session, Owned by the Composition Root

- **Never a module-level call.** `niquests.get(url)` opens a connection, uses it once and throws it
  away — no pooling, no shared configuration, and nothing to close on shutdown.
- **Build one `AsyncSession` (or `Session`) per application**, in the composition root, and pass it
  down. Connection reuse is most of the performance difference, and one session is also the one
  place headers, timeouts and TLS settings are configured.
- **Close it deterministically** — an exit stack or the framework's lifespan hook, never `atexit`.

```python
# WRONG — a fresh connection per call, configured by whatever the library defaults to
response = niquests.get(f"{orders_base_url}/orders/{order_id}")

# CORRECT — built once by the composition root, with the timeouts chosen and named there
session = niquests.AsyncSession(
    base_url=orders_base_url,
    timeout=TimeoutConfiguration(connect=_CONNECT_TIMEOUT_SECONDS, read=_READ_TIMEOUT_SECONDS),
)
response = await session.get(f"/orders/{order_id}")
```

## Timeouts

Why every call needs a deadline, and where it is configured, is in `python-boundaries`. The niquests
mechanics:

- **The library default was chosen for nobody; set yours.** Without a `timeout=` a request gets
  30 seconds to read, or 120 for a write method — numbers that fit no particular dependency.
- **`Session(timeout=TimeoutConfiguration(connect=..., read=...))`** sets it once; a per-call
  `timeout=` overrides it. A slow handshake and a slow body are different failures with different
  budgets, so give them separate numbers.

## Responses Are Checked, Not Assumed

- **`raise_for_status()`, or an explicit status check.** A `404` has a body and a truthy response
  object; code that goes straight to `.json()` will parse the error page and carry on.
- **Translate at the adapter.** The rest of the codebase must never see a library exception: convert
  transport errors and status errors into your own transient and permanent types, and let the retry
  policy key on those.
- **`.json()` gives you a shape, not a contract.** Validate it at the boundary before it travels
  inward.

## Redirects and TLS

- **Decide about redirects deliberately.** Following them is the default; for anything where the
  final URL matters — an API that signals with `301`, a preview page that redirects when access is
  refused — turn it off and read the status.
- **TLS**: leave `verify` at its default; a private CA goes in as `verify="/path/to/ca.pem"`. Why it
  stays on is in `python-security`.
- **A URL that came from a user**: pass `allow_redirects=False` and check each `Location` against
  the allowlist before following it — the reason is the SSRF rule in `python-security`.

## Retries

- **Leave the session's `retries=` at its default of `0`.** A retry is a policy decision and belongs
  beside the call, where it can see the translated error type — `python-tenacity` for the policy,
  `python-boundaries` for what may be retried. Transport retries underneath it multiply the budget.

## What Differs From `httpx`

- **`niquests` is a drop-in for `requests`**, so `session.get(...)` returns a response with
  `.status_code`, `.text`, `.json()`; `httpx` matches this closely but names some keywords
  differently — notably `allow_redirects` here versus `follow_redirects` there.
- Both support HTTP/2 and async. Pick one per codebase and do not mix: two HTTP stacks mean two
  places to configure timeouts, and one of them will be forgotten.
