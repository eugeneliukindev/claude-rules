"""Reports from the reports service."""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable

type Opener = Callable[[str, float], bytes]


def open_url(url: str, timeout: float) -> bytes:
    """Body of the response to a GET of `url`."""
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return response.read()


def fetch_report(
    report_id: int, *, base_url: str, timeout: float = 10.0, opener: Opener = open_url
) -> dict[str, object]:
    """The report `report_id` from the service at `base_url`, or at `REPORTS_URL` when it is set."""
    base_url = os.environ.get("REPORTS_URL", base_url)
    payload = json.loads(opener(f"{base_url.rstrip('/')}/reports/{report_id}", timeout))
    if not isinstance(payload, dict):
        raise TypeError("reports service answered with a non-object")
    return payload
