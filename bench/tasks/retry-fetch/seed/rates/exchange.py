"""Exchange rates from the rates service."""

from __future__ import annotations

from rates.http import Opener, get_json, open_url

RATES_URL = "https://rates.example.com/latest"


def fetch_exchange_rates(
    base: str, *, timeout: float = 5.0, opener: Opener = open_url
) -> dict[str, float]:
    """Rates of every currency against `base`."""
    payload = get_json(f"{RATES_URL}?base={base}", timeout=timeout, opener=opener)
    if not isinstance(payload, dict):
        raise TypeError("rates service answered with a non-object")
    return {code: float(rate) for code, rate in payload["rates"].items()}
