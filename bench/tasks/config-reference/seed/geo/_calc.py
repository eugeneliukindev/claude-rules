"""Great-circle distance."""

from __future__ import annotations

import math


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Kilometres between two points on the earth, along its surface."""
    if abs(lat1) > 90 or abs(lat2) > 90:
        raise ValueError("latitude beyond a pole")
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    half_dphi = (phi2 - phi1) / 2
    half_dlambda = math.radians(lon2 - lon1) / 2
    a = math.sin(half_dphi) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(half_dlambda) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))
