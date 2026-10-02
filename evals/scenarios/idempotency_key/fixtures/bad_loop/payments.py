import uuid

import httpx


def charge_customer(client: httpx.Client, customer_id: str) -> httpx.Response:
    for _attempt in range(3):
        key = uuid.uuid4().hex
        try:
            return client.post("/v1/charges", json={"customer_id": customer_id}, headers={"Idempotency-Key": key})
        except httpx.TimeoutException:
            continue
    raise RuntimeError(customer_id)
