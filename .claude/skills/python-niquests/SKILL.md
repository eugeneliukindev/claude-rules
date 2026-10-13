---
name: python-niquests
description: >-
  niquests mechanics for outbound HTTP, which carry over to httpx: one session from the root, a
  timeout on every request, status and transport errors translated, redirects, TLS. Use when code
  imports niquests or httpx, builds a session, or makes an outbound HTTP request.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# niquests

Checked against niquests 3.21. The API is `requests`-shaped, and the habits below carry over to
`httpx` almost unchanged — `allow_redirects` here is `follow_redirects` there. One HTTP stack per
codebase: two mean two places to configure timeouts. Timeouts and retries in general are
`python-boundaries`; the retry policy is `python-tenacity`; why a user's URL is checked on every
redirect is `python-security`.

### One session is built by the root and closed there, never a module-level call

**Why:** `niquests.get(url)` opens a connection, uses it once and throws it away — no pooling, no
shared configuration, nothing to close. One `AsyncSession` per application is where headers,
timeouts and TLS are configured once, and connection reuse is most of the performance difference.
It is closed by a `with` in the composition root or the lifespan, never `atexit`.

**Example:**
```python
# WRONG — a fresh connection per call, configured by whatever the library defaults to
async def fetch_shipment(shipment_id: ShipmentId, *, base_url: str) -> object:
    return niquests.get(f"{base_url}/shipments/{shipment_id}").json()


# CORRECT — the root's session, opened once and closed on the way out
@asynccontextmanager
async def managed_carrier_session(
    *, base_url: str, timeout: TimeoutConfiguration = _CARRIER_TIMEOUT
) -> AsyncIterator[niquests.AsyncSession]:
    async with niquests.AsyncSession(base_url=base_url, timeout=timeout) as session:
        yield session
```

### The session's timeout is chosen, with the connect and the read apart

**Why:** without `timeout=` a request gets 30 seconds to read, or 120 for a write method — numbers
that fit no dependency. A slow handshake and a slow body are different failures with different
budgets. A per-call `timeout=` overrides the session's only with a named constant.

**Example:**
```python
# WRONG — the library's numbers, one for every dependency
_CARRIER_TIMEOUT: Final = None


# CORRECT — this carrier's budgets, the connect and the read stated apart
_CARRIER_TIMEOUT: Final = TimeoutConfiguration(
    connect=_CARRIER_CONNECT_TIMEOUT_SECONDS, read=_CARRIER_READ_TIMEOUT_SECONDS
)
```

### A response is checked, and its errors translated at the adapter

**Why:** a `404` has a body and a truthy response object; code that goes straight to `.json()`
parses the error page and carries on. The rest of the codebase never sees a library exception:
transport failures and the listed statuses become the transient type, any other error the permanent
one, and the retry policy keys on those. `.json()` is a shape, validated before it travels inward.

**Example:**
```python
# WRONG — a 404's JSON error body comes back as the shipment, a timeout as niquests' own error
async def fetch_shipment(shipment_id: ShipmentId, *, session: niquests.AsyncSession) -> object:
    response = await session.get(f"/shipments/{shipment_id}")
    return response.json()


# CORRECT — transport failures and the listed statuses are transient, any other error permanent
async def fetch_shipment(shipment_id: ShipmentId, *, session: niquests.AsyncSession) -> object:
    try:
        response = await session.get(f"/shipments/{shipment_id}")
    except (niquests.ConnectionError, niquests.Timeout) as error:
        raise TransientCarrierError(f"fetching shipment {shipment_id} failed") from error
    if response.status_code in _TRANSIENT_STATUSES:
        raise TransientCarrierError(f"shipment {shipment_id}: {response.status_code}")
    if not response.ok:
        raise PermanentCarrierError(f"shipment {shipment_id}: {response.status_code}")
    return response.json()
```

### The session sends each request once: `retries=` stays at its default of `0`

**Why:** a retry belongs beside the call, where it sees the translated error type and knows whether
a write is idempotent; transport retries underneath a policy multiply its budget.

**Example:**
```python
# WRONG — retries inside the session, under a policy that already retries each call
def build_carrier_session(*, base_url: str) -> niquests.Session:
    return niquests.Session(base_url=base_url, retries=3)


# CORRECT — the session sends each request once; the policy beside the call decides
def build_carrier_session(*, base_url: str) -> niquests.Session:
    return niquests.Session(base_url=base_url)
```

### A redirect is followed by hand where the final URL matters

**Why:** following is the default; for an API that signals with `301`, or a user's URL whose every
hop must pass an allowlist, `allow_redirects=False` returns the redirect for the caller to inspect.
This is the niquests side of the `HttpFetcher` that `python-security` checks hop by hop.

**Example:**
```python
# WRONG — the client follows redirects, so the caller never sees a hop to check
@final
class NiquestsFetcher(HttpFetcher):
    def __init__(self, *, session: niquests.Session) -> None:
        self._session = session

    @override
    def get(self, url: str, *, follow_redirects: bool) -> HttpResponse:
        response = self._session.get(url)
        return HttpResponse(redirect_location=None, body=response.content or b"")


# CORRECT — redirects are returned to the caller when it asks to follow them itself
@final
class NiquestsFetcher(HttpFetcher):
    def __init__(self, *, session: niquests.Session) -> None:
        self._session = session

    @override
    def get(self, url: str, *, follow_redirects: bool) -> HttpResponse:
        response = self._session.get(url, allow_redirects=follow_redirects)
        location = response.headers.get("Location") if response.is_redirect else None
        return HttpResponse(redirect_location=location, body=response.content or b"")
```
