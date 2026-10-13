# Service-to-Service Credentials

### Each service has its own credential, and the token names the service it is for

**Why:** one static key shared by every caller cannot be rotated without a coordinated deploy or
revoked for one caller alone; a client-credentials token, a workload identity or mutual TLS is per
service. The token's `aud` names the receiving service, which verifies it like any other — a token
minted for one service and replayed against another is rejected. A user's token is not forwarded
across a trust boundary: inside one, the next service verifies it with its own audience in the
list or exchanges it; across one, the call uses the service's own credential. The client secret
comes from the environment or a secret manager (`python-security`).

**Example:**
```python
# WRONG — one shared key for every caller, sent as is
@final
class BillingClient:
    def __init__(self, *, http: BillingHttpClient, shared_api_key: str) -> None:
        self._http = http
        self._shared_api_key = shared_api_key

    async def invoice(self, document_id: DocumentId) -> Invoice:
        headers = {"X-Api-Key": self._shared_api_key}
        return await self._http.get_invoice(document_id, headers=headers)


# CORRECT — this service's own token, minted for the billing audience
@final
class BillingClient:
    def __init__(self, *, http: BillingHttpClient, tokens: ServiceTokenSource) -> None:
        self._http = http
        self._tokens = tokens

    async def invoice(self, document_id: DocumentId) -> Invoice:
        token = await self._tokens.token_for(audience=_BILLING_AUDIENCE)
        headers = {"Authorization": f"Bearer {token}"}
        return await self._http.get_invoice(document_id, headers=headers)
```

### An outbound token is fetched once and reused until shortly before its `exp`

**Why:** fetched per request, every call pays a round trip to the identity provider and its rate
limit; cached past its `exp`, every call fails. The client object the root owns keeps it, and
renews a safety margin before expiry.
