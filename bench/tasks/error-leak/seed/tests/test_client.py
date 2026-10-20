import json

from weather import current_temperature


def test_temperature() -> None:
    def opener(url: str, timeout: float) -> bytes:
        return json.dumps({"main": {"temp": 21.5, "humidity": 40}}).encode()

    assert current_temperature("Paris", opener=opener) == 21.5
