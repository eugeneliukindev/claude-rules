"""Hidden checks for rename-public: the new name works and the old one keeps working, with a warning."""

import warnings

import pytest

PARIS = (48.8566, 2.3522)
LONDON = (51.5074, -0.1278)


def test_gate_new_name() -> None:
    from geo import great_circle_km

    assert great_circle_km(PARIS, LONDON) == pytest.approx(343.5, abs=1)


def test_gate_route() -> None:
    from geo import route_length

    assert route_length([PARIS, LONDON]) == pytest.approx(343.5, abs=1)


def test_design_old_name_still_works_with_a_warning() -> None:
    import geo

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        distance = geo.distance_km(PARIS, LONDON)
    assert distance == pytest.approx(343.5, abs=1)
    assert any(issubclass(w.category, DeprecationWarning | FutureWarning) for w in caught)
