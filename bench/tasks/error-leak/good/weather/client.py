"""Readings from the weather service."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import quote

from weather.errors import WeatherError

type Opener = Callable[[str, float], bytes]

SERVICE_URL = "https://weather.example.com/v1/current"


def open_url(url: str, timeout: float) -> bytes:
    """Body of the response to a GET of `url`."""
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return response.read()


def current_temperature(city: str, *, timeout: float = 5.0, opener: Opener = open_url) -> float:
    """Air temperature in `city`, in degrees Celsius."""
    return _reading(city, "temp", timeout=timeout, opener=opener)


def current_humidity(city: str, *, timeout: float = 5.0, opener: Opener = open_url) -> float:
    """Relative humidity in `city`, in per cent."""
    return _reading(city, "humidity", timeout=timeout, opener=opener)


def _reading(city: str, key: str, *, timeout: float, opener: Opener) -> float:
    url = f"{SERVICE_URL}?city={quote(city)}"
    try:
        payload = json.loads(opener(url, timeout))
        return float(payload["main"][key])
    except (urllib.error.URLError, TimeoutError) as error:
        raise WeatherError(f"weather service is unreachable for {city!r}") from error
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise WeatherError(f"weather service answered unreadably for {city!r}") from error
