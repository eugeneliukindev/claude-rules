"""Books lent to members."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True, kw_only=True)
class Loan:
    """A book a member has borrowed until `due`."""

    book_id: int
    member_id: int
    due: date


class LoanRepository:
    """Loans kept in memory."""

    def __init__(self) -> None:
        self._loans: list[Loan] = []

    def put(self, loan: Loan) -> None:
        """Store `loan`."""
        self._loans.append(loan)

    def of_member(self, member_id: int) -> list[Loan]:
        """The loans of this member, oldest first."""
        return [loan for loan in self._loans if loan.member_id == member_id]


class LoanService:
    """Lends books and lists what members have borrowed."""

    def __init__(self, *, loans: LoanRepository) -> None:
        self._loans = loans

    def lend(self, book_id: int, member_id: int, due: date) -> None:
        """Record that `member_id` has `book_id` until `due`."""
        self._loans.put(Loan(book_id=book_id, member_id=member_id, due=due))

    def loans_of(self, member_id: int) -> list[Loan]:
        """What `member_id` has borrowed."""
        return self._loans.of_member(member_id)
