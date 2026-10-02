"""Load customers from the customer API."""

from dataclasses import dataclass
from http import HTTPStatus

from http_client import HttpClient, HttpError, HttpStatusError


class CustomerError(Exception):
    pass


class CustomerNotFoundError(CustomerError, LookupError):
    def __init__(self, customer_id: int) -> None:
        super().__init__(f"customer {customer_id} not found")
        self.customer_id = customer_id


class CustomerServiceError(CustomerError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class Customer:
    id: int
    name: str
    email: str


def load_customer(client: HttpClient, customer_id: int) -> Customer:
    try:
        body = client.get_json(f"/customers/{customer_id}")
    except HttpStatusError as error:
        if error.status_code == HTTPStatus.NOT_FOUND:
            raise CustomerNotFoundError(customer_id) from error
        raise CustomerServiceError(f"loading customer {customer_id} failed") from error
    except HttpError as error:
        raise CustomerServiceError(f"loading customer {customer_id} failed") from error
    return Customer(id=int(str(body["id"])), name=str(body["name"]), email=str(body["email"]))
