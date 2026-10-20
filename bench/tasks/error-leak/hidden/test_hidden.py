"""Hidden checks for error-leak: the new reading fails only with the package's own error."""

import json
import urllib.error

import pytest


def _answer(payload: object):
    def opener(url: str, timeout: float) -> bytes:
        return json.dumps(payload).encode()

    return opener


def _down(url: str, timeout: float) -> bytes:
    raise urllib.error.URLError("connection refused")


def _humidity():
    from weather.client import current_humidity

    return current_humidity


def test_gate_humidity() -> None:
    assert _humidity()("Paris", opener=_answer({"main": {"temp": 21.5, "humidity": 64}})) == 64


def test_design_network_failure_is_a_weather_error() -> None:
    from weather import WeatherError

    with pytest.raises(WeatherError) as caught:
        _humidity()("Paris", opener=_down)
    assert caught.value.__cause__ is not None


def test_design_unreadable_answer_is_a_weather_error() -> None:
    from weather import WeatherError

    with pytest.raises(WeatherError):
        _humidity()("Paris", opener=_answer({"main": {}}))
