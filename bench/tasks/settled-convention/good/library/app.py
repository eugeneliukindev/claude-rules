"""Builds the library's services."""

from __future__ import annotations

from library.books import BookRepo
from library.catalog import CatalogService
from library.loans import LoanRepo, LoanService
from library.members import MemberRepo
from library.membership import MembershipService


def build_catalog() -> CatalogService:
    """A catalogue with no books yet."""
    return CatalogService(books=BookRepo())


def build_membership() -> MembershipService:
    """A member list with nobody on it."""
    return MembershipService(members=MemberRepo())


def build_loans() -> LoanService:
    """A service with no loans yet."""
    return LoanService(loans=LoanRepo())
