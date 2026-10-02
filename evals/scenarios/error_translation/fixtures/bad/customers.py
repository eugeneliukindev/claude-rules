"""Load customers from the customer API."""

import logging
from dataclasses import dataclass

from http_client import HttpClient, HttpStatusError

logger = logging.getLogger(__name__)


class CustomerServiceError(Exception):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class Customer:
    id: int
    name: str
    email: str


def load_customer(client: HttpClient, customer_id: int) -> Customer | None:
    try:
        body = client.get_json(f"/customers/{customer_id}")
        return Customer(id=int(str(body["id"])), name=str(body["name"]), email=str(body["email"]))
    except HttpStatusError as error:
        if error.status_code == 404:
            return None
        raise CustomerServiceError("customer API failed")
    except Exception:
        logger.exception("failed")
        raise
