"""Hidden checks for settled-convention: loans work, and their store follows the codebase's naming."""

import importlib
import inspect
from datetime import date
from pathlib import Path

from library.app import build_loans


def test_gate_a_lent_book_is_listed() -> None:
    service = build_loans()
    service.lend(1, 7, date(2026, 11, 1))
    loans = list(service.loans_of(7))
    assert [(loan.book_id, loan.member_id, loan.due) for loan in loans] == [(1, 7, date(2026, 11, 1))]


def test_gate_other_members_have_no_loans() -> None:
    service = build_loans()
    service.lend(1, 7, date(2026, 11, 1))
    assert list(service.loans_of(8)) == []


def _classes() -> dict[str, type]:
    found = {}
    for path in Path("library").glob("*.py"):
        module = importlib.import_module(f"library.{path.stem}")
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__:
                found[name] = cls
    return found


def test_design_loan_store_follows_the_repo_naming() -> None:
    stores = [name for name in _classes() if name.startswith("Loan") and name not in {"Loan", "LoanService"}]
    assert stores == ["LoanRepo"], f"the codebase names stores ...Repo; found {stores}"
