# URLs From Outside

A URL from a user is fetched only if it passes an allowlist of schemes and hosts; internal metadata
ranges and loopback are blocked by default.

### The check is on the addresses the name resolves to, not on the name

**Why:** a public hostname whose DNS answers `169.254.169.254` passes every check of the string.
Every address the name resolves to must be global; the request then goes to the address that was
checked, since a second lookup can answer differently — an egress proxy enforcing the same rule
closes that gap.

**Example:**
```python
# WRONG — the name is checked, and a name that resolves to the metadata service passes
def require_allowed_url(url: str) -> None:
    host = urlsplit(url).hostname
    if host is None or host in _BLOCKED_HOSTS:
        raise ForbiddenUrlError(url)


# CORRECT — every address the name resolves to must be a public one
def require_allowed_url(url: str) -> None:
    host = urlsplit(url).hostname
    if host is None:
        raise ForbiddenUrlError(url)
    for *_, socket_address in socket.getaddrinfo(host, None):
        if not ipaddress.ip_address(socket_address[0]).is_global:
            raise ForbiddenUrlError(url)
```

### Redirects are followed by hand, and every hop is checked before it is requested

**Why:** the allowlist checked before the first request is worthless once the client follows a
redirect to `169.254.169.254` on its own.

**Example:**
```python
# WRONG — only the first URL is checked; a redirect to the metadata service is followed unchecked
def fetch_preview(url: str, *, fetcher: HttpFetcher) -> HttpResponse:
    require_allowed_url(url)
    return fetcher.get(url, follow_redirects=True)


# CORRECT — each hop is checked, and the chain is bounded
def fetch_preview(
    url: str, *, fetcher: HttpFetcher, max_redirects: int = _MAX_REDIRECTS
) -> HttpResponse:
    for _ in range(max_redirects):
        require_allowed_url(url)
        response = fetcher.get(url, follow_redirects=False)
        if response.redirect_location is None:
            return response
        url = urljoin(url, response.redirect_location)
    raise TooManyRedirectsError(url)
```
