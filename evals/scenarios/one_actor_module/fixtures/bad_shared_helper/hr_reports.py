from collections.abc import Iterable
from decimal import Decimal

from employees import Employee
from hours import split_hours


def hours_report(employees: Iterable[Employee]) -> list[tuple[str, Decimal, Decimal]]:
    return [(employee.employee_id, *split_hours(employee)) for employee in employees]
