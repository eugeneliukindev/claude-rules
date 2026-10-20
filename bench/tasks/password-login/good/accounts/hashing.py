"""Password hashing: the contract and its implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    """Turns a password into a stored hash and checks one against it."""

    @abstractmethod
    def hash(self, password: str) -> bytes:
        """A new hash of `password`, different each call."""

    @abstractmethod
    def verify(self, password: str, stored: bytes) -> bool:
        """Whether `password` produced `stored`."""


class ScryptHasher(PasswordHasher):
    """Salted scrypt; the salt is stored in front of the digest."""

    def __init__(self, *, cost: int = 2**14, block_size: int = 8, salt_size: int = 16) -> None:
        self._cost = cost
        self._block_size = block_size
        self._salt_size = salt_size

    def hash(self, password: str) -> bytes:
        import secrets

        salt = secrets.token_bytes(self._salt_size)
        return salt + self._digest(password, salt)

    def verify(self, password: str, stored: bytes) -> bool:
        import hmac

        salt, digest = stored[: self._salt_size], stored[self._salt_size :]
        return hmac.compare_digest(self._digest(password, salt), digest)

    def _digest(self, password: str, salt: bytes) -> bytes:
        import hashlib

        return hashlib.scrypt(password.encode(), salt=salt, n=self._cost, r=self._block_size, p=1)
