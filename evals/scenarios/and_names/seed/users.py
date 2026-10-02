"""User records and the repository contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class User:
    email: str
    password_hash: str
    display_name: str


class UserRepository(ABC):
    @abstractmethod
    def add(self, user: User) -> None: ...

    @abstractmethod
    def exists(self, email: str) -> bool: ...
