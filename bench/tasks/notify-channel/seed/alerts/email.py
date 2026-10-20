"""Alerts delivered by mail."""

from __future__ import annotations

from alerts.gateways import SmtpClient
from alerts.users import User


class EmailNotifier:
    """Delivers an alert to a user's mailbox."""

    def __init__(self, smtp: SmtpClient) -> None:
        self._smtp = smtp

    def notify(self, user: User, text: str) -> None:
        """Mail `text` to `user`."""
        self._smtp.send_mail(user.email, subject="Alert", body=text)
