"""Hidden checks for config-reference: the module moved, and so did the config that names it."""

import tomllib
from pathlib import Path

import pytest


def test_gate_new_module_works() -> None:
    from geo.distance import distance_km
    from geo.routes import route_km

    assert distance_km(48.8566, 2.3522, 51.5074, -0.1278) == pytest.approx(343.5, abs=1)
    assert route_km([(0.0, 0.0), (0.0, 1.0)]) == pytest.approx(111.2, abs=0.5)


def test_gate_old_module_is_gone() -> None:
    assert not Path("geo/_calc.py").exists()


def test_design_config_names_the_new_path() -> None:
    ignores = tomllib.loads(Path("pyproject.toml").read_text())["tool"]["ruff"]["lint"]["per-file-ignores"]
    assert "geo/_calc.py" not in ignores, "config still names the old module"
    assert "geo/distance.py" in ignores, "the new module lost its exception"
