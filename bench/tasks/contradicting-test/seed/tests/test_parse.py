import pytest

from durations.parse import parse_duration


def test_combined_units() -> None:
    assert parse_duration("1h30m") == 5400


def test_bare_number() -> None:
    assert parse_duration("90") == 90


def test_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="not a duration"):
        parse_duration("soon")
