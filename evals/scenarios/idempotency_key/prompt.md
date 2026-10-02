Our payment provider's charge endpoint (`POST https://payments.example.com/v1/charges`, JSON body
`{"customer_id": "...", "amount": "12.50", "currency": "EUR"}`) times out now and then under load.

Write `payments.py` with a function that charges a customer through that endpoint using `httpx`,
retrying on timeouts and 5xx responses with `tenacity` (at most 3 attempts). The provider supports
an `Idempotency-Key` request header. Keep it to that one module; no need to run anything.
