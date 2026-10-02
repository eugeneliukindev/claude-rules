"""Client for the supplier's price API."""

from decimal import Decimal

import httpx


class SupplierError(Exception):
    """The supplier could not return a price."""


class SupplierClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def fetch_price(self, sku: str) -> Decimal:
        try:
            response = self._http.get(f"/prices/{sku}", timeout=10)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupplierError(f"Price for {sku} unavailable") from error
        return Decimal(response.json()["price"])
