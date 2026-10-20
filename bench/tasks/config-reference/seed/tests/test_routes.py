import pytest

from geo.routes import route_km


def test_paris_london() -> None:
    assert route_km([(48.8566, 2.3522), (51.5074, -0.1278)]) == pytest.approx(343.5, abs=1)
