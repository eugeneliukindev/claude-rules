"""Human durations."""

from __future__ import annotations

import re

_PART = re.compile(r"(\d+)([hms])")
_SECONDS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text: str) -> int:
    """Seconds in `text`, like `1h30m`; a bare number means minutes."""
    text = text.strip()
    if text.isdigit():
        return int(text) * 60
    parts = _PART.findall(text)
    if not parts or "".join(number + unit for number, unit in parts) != text:
        raise ValueError(f"not a duration: {text!r}")
    return sum(int(number) * _SECONDS[unit] for number, unit in parts)
