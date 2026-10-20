"""Users and where they are kept."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class User:
    """Someone with an account."""

    email: str
    password_hash: bytes = b""


class UserStore(ABC):
    """Where users are kept."""

    @abstractmethod
    def find(self, email: str) -> User | None:
        """The user with this email, or `None`."""

    @abstractmethod
    def save(self, user: User) -> None:
        """Store `user`, replacing one with the same email."""


class InMemoryUsers(UserStore):
    """Users kept in a dict, for one process."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def find(self, email: str) -> User | None:
        return self._users.get(email)

    def save(self, user: User) -> None:
        self._users[user.email] = user
