from decimal import Decimal

from employees import Employee

_OVERTIME_THRESHOLD_HOURS = Decimal(160)


def calculate_pay(employee: Employee) -> Decimal:
    overtime_hours = max(employee.hours_worked - _OVERTIME_THRESHOLD_HOURS, Decimal(0))
    regular_hours = employee.hours_worked - overtime_hours
    return employee.hourly_rate * (regular_hours + overtime_hours * Decimal("1.5"))
