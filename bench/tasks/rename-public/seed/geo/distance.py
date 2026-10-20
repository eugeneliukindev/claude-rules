"""Distance between two coordinates."""

from __future__ import annotations

import math

type Point = tuple[float, float]

EARTH_RADIUS_KM = 6371.0088


def distance_km(a: Point, b: Point) -> float:
    """Great-circle distance between `a` and `b`, as (latitude, longitude) in degrees."""
    for latitude, _ in (a, b):
        if not -90 <= latitude <= 90:
            raise ValueError(f"latitude {latitude} is outside -90..90")
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (*a, *b))
    h = math.sin((lat_b - lat_a) / 2) ** 2
    h += math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))
