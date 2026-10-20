"""Hidden checks for retry-fetch: the job survives a hiccup and still fails loudly."""

import json
import time
import urllib.error

import pytest

PAYLOAD = json.dumps({"rates": {"EUR": "0.9"}}).encode()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


class Flaky:
    def __init__(self, failures: list[Exception]) -> None:
        self.failures = failures
        self.calls: list[float] = []

    def __call__(self, url: str, timeout: float) -> bytes:
        self.calls.append(timeout)
        if self.failures:
            raise self.failures.pop(0)
        return PAYLOAD


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://rates.example.com", code, "error", None, None)  # type: ignore[arg-type]


def test_gate_recovers_from_a_hiccup() -> None:
    from rates.exchange import fetch_exchange_rates

    opener = Flaky([urllib.error.URLError("reset"), _http_error(503)])
    assert fetch_exchange_rates("USD", opener=opener) == {"EUR": 0.9}


def test_gate_refusal_is_not_repeated() -> None:
    from rates.exchange import fetch_exchange_rates

    opener = Flaky([_http_error(404)])
    with pytest.raises(Exception):  # noqa: B017, PT011
        fetch_exchange_rates("USD", opener=opener)
    assert len(opener.calls) == 1


def test_gate_gives_up_loudly() -> None:
    from rates.exchange import fetch_exchange_rates

    opener = Flaky([urllib.error.URLError("down")] * 50)
    with pytest.raises(Exception):  # noqa: B017, PT011
        fetch_exchange_rates("USD", opener=opener)
    assert 2 <= len(opener.calls) <= 10


def test_gate_every_attempt_has_a_timeout() -> None:
    from rates.exchange import fetch_exchange_rates

    opener = Flaky([urllib.error.URLError("reset")])
    fetch_exchange_rates("USD", opener=opener)
    assert all(timeout and timeout > 0 for timeout in opener.calls)
