"""What can be done with an account."""

from __future__ import annotations

from accounts.hashing import PasswordHasher
from accounts.users import User, UserStore


class AccountService:
    """Finds and creates accounts."""

    def __init__(self, *, users: UserStore, hasher: PasswordHasher) -> None:
        self._users = users
        self._hasher = hasher

    def find(self, email: str) -> User | None:
        """The account with this email, or `None`."""
        return self._users.find(email)

    def register(self, email: str, password: str) -> None:
        """Create an account that logs in with `password`."""
        self._users.save(User(email=email, password_hash=self._hasher.hash(password)))

    def log_in(self, email: str, password: str) -> bool:
        """Whether `password` is the one this account was created with."""
        user = self._users.find(email)
        return user is not None and self._hasher.verify(password, user.password_hash)
