"""Raising alerts."""

from __future__ import annotations

from collections.abc import Mapping
from abc import ABC, abstractmethod

from alerts.users import Channel, User


class Notifier(ABC):
    """Delivers an alert by one channel."""

    @abstractmethod
    def notify(self, user: User, text: str) -> None:
        """Deliver `text` to `user`."""


class AlertService:
    """Raises alerts for users, each by the channel they chose."""

    def __init__(self, notifiers: Mapping[Channel, Notifier]) -> None:
        self._notifiers = notifiers

    def alert(self, user: User, text: str) -> None:
        """Deliver `text` to `user`."""
        self._notifiers[user.channel].notify(user, text)
