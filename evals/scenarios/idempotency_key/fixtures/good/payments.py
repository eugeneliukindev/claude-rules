import uuid

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt


def charge_customer(client: httpx.Client, customer_id: str, amount: str) -> dict[str, object]:
    idempotency_key = str(uuid.uuid4())
    return _post_charge(client, {"customer_id": customer_id, "amount": amount}, idempotency_key)


@retry(stop=stop_after_attempt(3), retry=retry_if_exception_type(httpx.TimeoutException), reraise=True)
def _post_charge(client: httpx.Client, payload: dict[str, str], idempotency_key: str) -> dict[str, object]:
    response = client.post("/v1/charges", json=payload, headers={"Idempotency-Key": idempotency_key})
    response.raise_for_status()
    return response.json()
