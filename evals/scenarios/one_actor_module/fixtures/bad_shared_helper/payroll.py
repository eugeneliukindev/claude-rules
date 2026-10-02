from decimal import Decimal

from employees import Employee
from hours import split_hours


def calculate_pay(employee: Employee) -> Decimal:
    regular, overtime = split_hours(employee)
    return employee.hourly_rate * (regular + overtime * Decimal("1.5"))
