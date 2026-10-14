---
name: python-niquests
description: >-
  niquests mechanics for outbound HTTP, which carry over to httpx: one session opened by the root, a
  timeout on every request, status and transport errors translated, retries off, redirects by hand.
  Use when code imports niquests or httpx, builds a session, or makes an outbound HTTP request. Not
  for when to retry (python-boundaries).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# niquests

Checked against niquests 3.21. The API is `requests`-shaped, and the habits below carry over to
`httpx` almost unchanged — `allow_redirects` here is `follow_redirects` there; `AsyncSession` under
`async with` is the same as `Session` under `with`. One HTTP stack per codebase: two mean two places
to configure timeouts. When to retry and how long to wait are `python-boundaries`; why a user's URL
is checked on every redirect is `python-security`.

### One session is opened by the root's `with` and handed down, never a module-level call

**Why:** `niquests.get(url)` opens a connection, uses it once and throws it away — no pooling, no
shared configuration. One `Session` per application is where the base URL, headers, timeouts and TLS
are configured once, and connection reuse is most of the performance difference. The session is its
own context manager; the root enters it, and nothing wraps it or closes it from `atexit`.

**Example:**
```python
# WRONG — a fresh connection per call, configured by whatever the library defaults to
def fetch_departures(stop_id: StopId, *, departures_url: str) -> object:
    return niquests.get(f"{departures_url}/stops/{stop_id}/departures").json()


# CORRECT — the root opens the session once, and every adapter is handed the same one
def main() -> None:
    settings = Settings()
    with niquests.Session(
        base_url=settings.departures_url, timeout=_DEPARTURES_TIMEOUT
    ) as session:
        serve_departure_board(DepartureBoard(session=session), port=settings.port)
```

### The session's timeout is chosen, with the connect and the read apart

**Why:** without `timeout=` a request gets 30 seconds to read, or 120 for a write method — numbers
that fit no dependency. A slow handshake and a slow body are different failures with different
budgets. A per-call `timeout=` overrides the session's only with a named constant.

**Example:**
```python
# WRONG — the library's numbers, one for every dependency
_DEPARTURES_TIMEOUT: Final = None


# CORRECT — this feed's budgets, the connect and the read stated apart
_DEPARTURES_TIMEOUT: Final = niquests.TimeoutConfiguration(
    connect=_DEPARTURES_CONNECT_TIMEOUT_SECONDS, read=_DEPARTURES_READ_TIMEOUT_SECONDS
)
```

### A response is checked, and its errors translated at the adapter

**Why:** a `404` has a body and a truthy response object; code that goes straight to `.json()`
parses the error page and carries on. The rest of the codebase never sees a library exception:
`niquests.ConnectionError` and `niquests.Timeout` — both `OSError`s — and the listed statuses become
the transient type, any other error status the permanent one, and the retry policy keys on those.
`.json()` is a shape, validated before it travels inward.

**Example:**
```python
# WRONG — a 404's JSON error body comes back as the departures, a timeout as niquests' own error
def fetch_departures(stop_id: StopId, *, session: niquests.Session) -> object:
    response = session.get(f"/stops/{stop_id}/departures")
    return response.json()


# CORRECT — transport failures and the listed statuses are transient, any other error permanent
def fetch_departures(stop_id: StopId, *, session: niquests.Session) -> object:
    try:
        response = session.get(f"/stops/{stop_id}/departures")
    except (niquests.ConnectionError, niquests.Timeout) as error:
        raise DepartureFeedUnavailableError(stop_id) from error
    if response.status_code in _TRANSIENT_STATUSES:
        raise DepartureFeedUnavailableError(stop_id, status_code=response.status_code)
    if not response.ok:
        raise DepartureFeedRejectedError(stop_id, status_code=response.status_code)
    return response.json()
```

### The session sends each request once: `retries=` stays at its default of `0`

**Why:** a retry belongs beside the call, where it sees the translated error type and knows whether
a write is idempotent; `retries=3` or a `RetryConfiguration` underneath a policy multiplies its
budget, and the policy's attempt count stops meaning anything.

### A redirect is followed by hand where the final URL matters

**Why:** following is the default; for an API that signals with `301`, or a user's URL whose every
hop must pass an allowlist, `allow_redirects=False` returns the redirect for the caller to inspect.
`Location` may be relative, so it is joined to the URL that answered.

**Example:**
```python
# WRONG — the session follows every redirect, so the caller never sees a hop to check
def fetch_feed_hop(feed_url: str, *, session: niquests.Session) -> FeedHop:
    response = session.get(feed_url)
    return FeedHop(next_url=None, body=response.content or b"")


# CORRECT — the redirect comes back, and the caller checks the next URL before it follows
def fetch_feed_hop(feed_url: str, *, session: niquests.Session) -> FeedHop:
    response = session.get(feed_url, allow_redirects=False)
    if not response.is_redirect:
        return FeedHop(next_url=None, body=response.content or b"")
    return FeedHop(next_url=urljoin(feed_url, response.headers["Location"]), body=b"")
```
