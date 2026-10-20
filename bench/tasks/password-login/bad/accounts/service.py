"""What can be done with an account."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from accounts.users import User, UserStore


class AccountService:
    """Finds and creates accounts."""

    def __init__(self, *, users: UserStore, salt_size: int = 16) -> None:
        self._users = users
        self._salt_size = salt_size

    def find(self, email: str) -> User | None:
        """The account with this email, or `None`."""
        return self._users.find(email)

    def register(self, email: str, password: str) -> None:
        """Create an account that logs in with `password`."""
        salt = secrets.token_bytes(self._salt_size)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        self._users.save(User(email=email, password_hash=salt + digest))

    def log_in(self, email: str, password: str) -> bool:
        """Whether `password` is the one this account was created with."""
        user = self._users.find(email)
        if user is None:
            return False
        salt, digest = user.password_hash[: self._salt_size], user.password_hash[self._salt_size :]
        candidate = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(candidate, digest)
