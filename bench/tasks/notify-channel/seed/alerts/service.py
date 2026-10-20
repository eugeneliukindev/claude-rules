"""Raising alerts."""

from __future__ import annotations

from alerts.email import EmailNotifier
from alerts.users import User


class AlertService:
    """Raises alerts for users."""

    def __init__(self, notifier: EmailNotifier) -> None:
        self._notifier = notifier

    def alert(self, user: User, text: str) -> None:
        """Deliver `text` to `user`."""
        self._notifier.notify(user, text)
