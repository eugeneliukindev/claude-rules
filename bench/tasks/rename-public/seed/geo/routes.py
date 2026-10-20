"""Length of a route through several points."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise

from geo.distance import Point, distance_km


def route_length(points: Iterable[Point]) -> float:
    """Sum of the distances between consecutive `points`, in kilometres."""
    return sum(distance_km(a, b) for a, b in pairwise(points))
