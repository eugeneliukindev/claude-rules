---
name: python-niquests
description: >-
  niquests HTTP client practice, which transfers to httpx almost unchanged: one session owned by
  the composition root instead of module-level calls, a timeout on every request, raise_for_status
  rather than assuming success, transport and status errors translated at the adapter, deliberate
  redirect handling, TLS verification left on, and where retries belong. Use when Python code
  imports niquests or httpx, builds a session, or makes an outbound HTTP request.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
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
- **Close it deterministically** — a `with` block in the composition root or the framework's
  lifespan hook, never `atexit`.

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

Every request has an explicit timeout, set once on the session and overridden per call only with a
named constant (why: `python-boundaries`). The niquests mechanics:

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

```python
# WRONG — a 404's JSON error body comes back as the order, a timeout as niquests' own exception
async def fetch_order(session: niquests.AsyncSession, order_id: OrderId) -> object:
    response = await session.get(f"/orders/{order_id}")
    return response.json()

# CORRECT — transport failures and the listed statuses are transient, any other error permanent
async def fetch_order(session: niquests.AsyncSession, order_id: OrderId) -> object:
    try:
        response = await session.get(f"/orders/{order_id}")
    except (niquests.ConnectionError, niquests.Timeout) as error:
        raise TransientUpstreamError(f"Fetching order {order_id} failed") from error
    if response.status_code in _TRANSIENT_STATUSES:
        raise TransientUpstreamError(f"Fetching order {order_id} returned {response.status_code}")
    if not response.ok:
        raise PermanentUpstreamError(f"Fetching order {order_id} returned {response.status_code}")
    return response.json()
```

- **`.json()` gives you a shape, not a contract.** Validate it at the boundary before it travels
  inward.

## Redirects

- **Decide about redirects deliberately.** Following them is the default; for anything where the
  final URL matters — an API that signals with `301`, a preview page that redirects when access is
  refused — turn it off and read the status.
- **A URL that came from a user**: pass `allow_redirects=False` and check each `Location` against
  the allowlist before following it — the reason is the SSRF rule in `python-security`.

```python
# WRONG — the allowlist saw only the first URL; every redirect after it is followed unchecked
def fetch_preview(session: niquests.Session, url: str) -> niquests.Response:
    _ensure_allowed(url)
    return session.get(url)

# CORRECT — redirects are off, and every Location is checked before it is requested
def fetch_preview(session: niquests.Session, url: str) -> niquests.Response:
    for _ in range(_MAX_REDIRECTS + 1):
        _ensure_allowed(url)
        response = session.get(url, allow_redirects=False)
        if not response.is_redirect:
            return response
        url = urljoin(url, response.headers["Location"])
    raise TooManyRedirectsError(f"{url} redirected more than {_MAX_REDIRECTS} times")
```

## TLS

- **Leave `verify` at its default**; a private CA goes in as `verify="/path/to/ca.pem"`. Why it
  stays on is in `python-security`.

```python
# WRONG — silences one private CA's error by accepting every certificate, an attacker's included
session = niquests.Session(verify=False)

# CORRECT — the private CA is trusted explicitly, and verification stays on
session = niquests.Session(verify=ca_bundle_path)
```

## Retries

- **Leave the session's `retries=` at its default of `0`.** A retry is a policy decision and belongs
  beside the call, where it can see the translated error type, and it retries only transient
  failures and a write only when it is idempotent (why: `python-boundaries`; the policy:
  `python-tenacity`). Transport retries underneath it multiply the budget.

```python
# WRONG — retries inside the session, under a policy that already retries each call
session = niquests.Session(base_url=orders_base_url, retries=3)

# CORRECT — the session sends each request once; the policy beside the call decides
session = niquests.Session(base_url=orders_base_url)
```

## What Differs From `httpx`

- **`niquests` is a drop-in for `requests`**, so `session.get(...)` returns a response with
  `.status_code`, `.text`, `.json()`; `httpx` matches this closely but names some keywords
  differently — notably `allow_redirects` here versus `follow_redirects` there.
- Both support HTTP/2 and async. Pick one per codebase and do not mix: two HTTP stacks mean two
  places to configure timeouts, and one of them will be forgotten.
