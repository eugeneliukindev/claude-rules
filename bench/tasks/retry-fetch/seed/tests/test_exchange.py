import json

from rates.exchange import fetch_exchange_rates


def test_reads_rates() -> None:
    def opener(url: str, timeout: float) -> bytes:
        return json.dumps({"rates": {"EUR": "0.9"}}).encode()

    assert fetch_exchange_rates("USD", opener=opener) == {"EUR": 0.9}
