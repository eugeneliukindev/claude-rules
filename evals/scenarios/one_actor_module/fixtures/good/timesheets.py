from collections.abc import Iterable
from decimal import Decimal

from employees import Employee

_OVERTIME_THRESHOLD_HOURS = Decimal(160)


def report_hours(employees: Iterable[Employee]) -> list[tuple[str, Decimal, Decimal]]:
    rows = []
    for employee in employees:
        overtime_hours = max(employee.hours_worked - _OVERTIME_THRESHOLD_HOURS, Decimal(0))
        rows.append((employee.employee_id, employee.hours_worked - overtime_hours, overtime_hours))
    return rows
