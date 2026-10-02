from decimal import Decimal

from employees import Employee


def split_hours(employee: Employee) -> tuple[Decimal, Decimal]:
    overtime = max(employee.hours_worked - 160, Decimal(0))
    return employee.hours_worked - overtime, overtime
