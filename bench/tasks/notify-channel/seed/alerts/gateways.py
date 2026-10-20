"""Clients of the services that deliver messages."""

from __future__ import annotations


class SmtpClient:
    """Sends mail through the mail relay."""

    def send_mail(self, to: str, subject: str, body: str) -> None:
        """Hand one message to the relay."""
        raise NotImplementedError("the relay is configured in production")


class SmsGateway:
    """Sends text messages through the SMS provider."""

    def send(self, phone: str, text: str) -> None:
        """Hand one text message to the provider."""
        raise NotImplementedError("the provider is configured in production")
