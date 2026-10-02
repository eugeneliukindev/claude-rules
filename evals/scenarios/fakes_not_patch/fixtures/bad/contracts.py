"""Contracts the registration service depends on."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class User:
    email: str


class UserRepository(ABC):
    @abstractmethod
    def exists(self, email: str) -> bool: ...

    @abstractmethod
    def add(self, user: User) -> None: ...


class Mailer(ABC):
    @abstractmethod
    def send_welcome(self, user: User) -> None: ...
