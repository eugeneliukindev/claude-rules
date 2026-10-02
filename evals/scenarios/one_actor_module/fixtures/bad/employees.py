"""The employee record shared across the company's systems."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Employee:
    employee_id: str
    name: str
    hourly_rate: Decimal
    hours_worked: Decimal  # this month
