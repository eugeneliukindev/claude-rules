"""JSON over HTTP, with failures sorted into transient and permanent."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

type Opener = Callable[[str, float], bytes]


class TransientError(Exception):
    """The network or the server failed in a way a later attempt may not."""


class PermanentError(Exception):
    """The server refused the request, and sending it again changes nothing."""


def open_url(url: str, timeout: float) -> bytes:
    """Body of the response to a GET of `url`."""
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return response.read()


def get_json(url: str, *, timeout: float, opener: Opener = open_url) -> object:
    """Decoded JSON body of a GET of `url`."""
    try:
        body = opener(url, timeout)
    except urllib.error.HTTPError as error:
        if error.code >= 500:
            raise TransientError(f"{url} answered {error.code}") from error
        raise PermanentError(f"{url} answered {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise TransientError(f"{url} is unreachable") from error
    return json.loads(body)
