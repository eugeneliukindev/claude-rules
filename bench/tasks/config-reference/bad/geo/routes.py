"""Lengths of routes."""

from __future__ import annotations

from itertools import pairwise

from geo.distance import distance_km


def route_km(points: list[tuple[float, float]]) -> float:
    """Kilometres along the route through `points`."""
    return sum(distance_km(*a, *b) for a, b in pairwise(points))
