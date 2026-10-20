"""The client the Stripe SDK would give us; kept small here."""

from __future__ import annotations


class StripeClient:
    """Talks to Stripe."""

    def create_charge(self, *, amount_cents: int, currency: str, source: str) -> str:
        """Charge `source` and return the charge id."""
        raise NotImplementedError("configured in production")
