from collections.abc import Iterable
from decimal import Decimal

from employees import Employee


def calculate_pay(employee: Employee) -> Decimal:
    regular, overtime = _split_hours(employee)
    return employee.hourly_rate * (regular + overtime * Decimal("1.5"))


def build_hours_report(employees: Iterable[Employee]) -> list[tuple[str, Decimal, Decimal]]:
    return [(employee.employee_id, *_split_hours(employee)) for employee in employees]


def _split_hours(employee: Employee) -> tuple[Decimal, Decimal]:
    overtime = max(employee.hours_worked - 160, Decimal(0))
    return employee.hours_worked - overtime, overtime
