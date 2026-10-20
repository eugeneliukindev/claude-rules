"""Exchange rates from the rates service."""

from __future__ import annotations

import time

from rates.http import Opener, TransientError, get_json, open_url

RATES_URL = "https://rates.example.com/latest"


def fetch_exchange_rates(
    base: str,
    *,
    timeout: float = 5.0,
    attempts: int = 3,
    backoff: float = 0.5,
    opener: Opener = open_url,
) -> dict[str, float]:
    """Rates of every currency against `base`, asking again after a transient failure."""
    url = f"{RATES_URL}?base={base}"
    for attempt in range(attempts):
        try:
            payload = get_json(url, timeout=timeout, opener=opener)
            break
        except TransientError:
            if attempt == attempts - 1:
                raise
            time.sleep(backoff * 2**attempt)
    if not isinstance(payload, dict):
        raise TypeError("rates service answered with a non-object")
    return {code: float(rate) for code, rate in payload["rates"].items()}
