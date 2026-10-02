import uuid

import httpx
from tenacity import retry, stop_after_attempt


@retry(stop=stop_after_attempt(3))
def charge_customer(client: httpx.Client, customer_id: str, amount: str) -> dict[str, object]:
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    response = client.post("/v1/charges", json={"customer_id": customer_id}, headers=headers)
    response.raise_for_status()
    return response.json()
