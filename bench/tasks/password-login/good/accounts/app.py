"""Builds the account service."""

from __future__ import annotations

from accounts.hashing import ScryptHasher
from accounts.service import AccountService
from accounts.users import InMemoryUsers


def build_service() -> AccountService:
    """A ready service with its own store."""
    return AccountService(users=InMemoryUsers(), hasher=ScryptHasher())
