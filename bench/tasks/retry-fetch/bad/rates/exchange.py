"""Exchange rates from the rates service."""

from __future__ import annotations

import time

from rates.http import Opener, get_json, open_url

RATES_URL = "https://rates.example.com/latest"


def fetch_exchange_rates(
    base: str, *, timeout: float = 5.0, opener: Opener = open_url
) -> dict[str, float]:
    """Rates of every currency against `base`."""
    payload = None
    for _ in range(5):
        try:
            payload = get_json(f"{RATES_URL}?base={base}", timeout=timeout, opener=opener)
            break
        except Exception:
            time.sleep(2)
    if not isinstance(payload, dict):
        return {}
    return {code: float(rate) for code, rate in payload["rates"].items()}
