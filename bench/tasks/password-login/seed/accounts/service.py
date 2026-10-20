"""What can be done with an account."""

from __future__ import annotations

from accounts.users import User, UserStore


class AccountService:
    """Finds and creates accounts."""

    def __init__(self, *, users: UserStore) -> None:
        self._users = users

    def find(self, email: str) -> User | None:
        """The account with this email, or `None`."""
        return self._users.find(email)
