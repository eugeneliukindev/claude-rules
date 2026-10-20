"""Orders customers place."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Order:
    """An order waiting for payment."""

    id: int
    total: Decimal
    currency: str
