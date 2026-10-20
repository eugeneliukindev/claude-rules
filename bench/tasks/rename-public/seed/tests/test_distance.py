import pytest

from geo import distance_km, route_length

PARIS = (48.8566, 2.3522)
LONDON = (51.5074, -0.1278)


def test_paris_london() -> None:
    assert distance_km(PARIS, LONDON) == pytest.approx(343.5, abs=1)


def test_route() -> None:
    assert route_length([PARIS, LONDON, PARIS]) == pytest.approx(687, abs=2)
