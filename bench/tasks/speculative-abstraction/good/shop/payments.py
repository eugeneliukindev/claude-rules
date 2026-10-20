"""Paying for orders."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shop.orders import Order
from shop.stripe_client import StripeClient

CENTS_PER_UNIT = 100


class PaymentGateway(ABC):
    """Takes payments for orders."""

    @abstractmethod
    def charge(self, order: Order, *, card_token: str) -> str:
        """Charge `order` to the card behind `card_token` and return the charge id."""


class StripeGateway(PaymentGateway):
    """Payments through Stripe."""

    def __init__(self, client: StripeClient) -> None:
        self._client = client

    def charge(self, order: Order, *, card_token: str) -> str:
        """Charge `order` through Stripe."""
        return self._client.create_charge(
            amount_cents=int(order.total * CENTS_PER_UNIT),
            currency=order.currency,
            source=card_token,
        )


def charge(order: Order, *, card_token: str, client: StripeClient) -> str:
    """Charge `order` to the card behind `card_token` and return the charge id."""
    return StripeGateway(client).charge(order, card_token=card_token)
