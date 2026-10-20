"""Alerts delivered by text message."""

from __future__ import annotations

from alerts.gateways import SmsGateway
from alerts.service import Notifier
from alerts.users import User


class SmsNotifier(Notifier):
    """Delivers an alert to a user's phone."""

    def __init__(self, gateway: SmsGateway) -> None:
        self._gateway = gateway

    def notify(self, user: User, text: str) -> None:
        """Text `text` to `user`."""
        if user.phone is None:
            raise ValueError(f"user {user.id} chose text messages but has no phone")
        self._gateway.send(user.phone, text)
