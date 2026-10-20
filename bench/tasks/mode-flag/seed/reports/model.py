"""A sales report."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Row:
    """Sales of one product."""

    product: str
    units: int
    revenue: float


@dataclass(frozen=True, slots=True, kw_only=True)
class Report:
    """Sales over one period."""

    period: str
    rows: tuple[Row, ...]
