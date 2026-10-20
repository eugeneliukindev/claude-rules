"""The shopping cart."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, kw_only=True)
class Line:
    """One product in the cart."""

    sku: str
    unit_price: float
    quantity: int = 1


@dataclass(slots=True)
class Cart:
    """Products a customer is about to buy."""

    lines: list[Line] = field(default_factory=list)

    def add(self, line: Line) -> None:
        """Put `line` into the cart."""
        self.lines.append(line)

    @property
    def total(self) -> float:
        """What the cart costs."""
        return round(sum(line.unit_price * line.quantity for line in self.lines), 2)
