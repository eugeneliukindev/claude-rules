"""The nightly job that stores the day's rates."""

from __future__ import annotations

import json
from pathlib import Path

from rates.exchange import fetch_exchange_rates


def store_rates(base: str, target: Path) -> None:
    """Write today's rates against `base` to `target`."""
    target.write_text(json.dumps(fetch_exchange_rates(base)), encoding="utf-8")
