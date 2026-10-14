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
def require_public_artwork_url(url: str) -> None:
    host = urlsplit(url).hostname
    if host is None or host in _BLOCKED_HOSTS:
        raise ArtworkUrlRefusedError(url)


# CORRECT — every address the name resolves to must be a public one
def require_public_artwork_url(url: str) -> None:
    host = urlsplit(url).hostname
    if host is None:
        raise ArtworkUrlRefusedError(url)
    for *_, socket_address in socket.getaddrinfo(host, None):
        if not ipaddress.ip_address(socket_address[0]).is_global:
            raise ArtworkUrlRefusedError(url)
```

### Redirects are followed by hand, and every hop is checked before it is requested

**Why:** the allowlist checked before the first request is worthless once the client follows a
redirect to `169.254.169.254` on its own.

**Example:**
```python
# WRONG — only the first URL is checked; a redirect to the metadata service is followed unchecked
def download_artwork(
    url: str, *, downloads: ArtworkDownloads, max_redirects: int = _MAX_REDIRECTS
) -> ArtworkDownload:
    require_public_artwork_url(url)
    return downloads.get(url, max_redirects=max_redirects)


# CORRECT — each hop is checked, and the chain is bounded
def download_artwork(
    url: str, *, downloads: ArtworkDownloads, max_redirects: int = _MAX_REDIRECTS
) -> ArtworkDownload:
    for _ in range(max_redirects):
        require_public_artwork_url(url)
        download = downloads.get(url, max_redirects=0)
        if download.next_hop is None:
            return download
        url = urljoin(url, download.next_hop)
    raise ArtworkRedirectsExceededError(url)
```
