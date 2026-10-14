# URLs From Outside

A URL from a user is fetched only if it passes an allowlist of schemes and hosts; internal metadata
ranges and loopback are blocked by default.

### Every hop is checked on the addresses its name resolves to, and redirects are followed by hand

**Why:** a public hostname whose DNS answers `169.254.169.254` passes every check of the string, and
the allowlist checked before the first request is worthless once the client follows a redirect there
on its own. Every address the name resolves to must be global, on every hop and before it is
requested, with the chain bounded; the request then goes to the address that was checked, since a
second lookup can answer differently — an egress proxy enforcing the same rule closes that gap.

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
