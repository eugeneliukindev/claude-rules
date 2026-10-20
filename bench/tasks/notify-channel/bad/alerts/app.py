"""Builds the alert service from the delivery clients."""

from __future__ import annotations

from alerts.email import EmailNotifier
from alerts.gateways import SmsGateway, SmtpClient
from alerts.service import AlertService


def build_service(smtp: SmtpClient, sms: SmsGateway) -> AlertService:
    """The alert service the application uses."""
    return AlertService(EmailNotifier(smtp), sms)
