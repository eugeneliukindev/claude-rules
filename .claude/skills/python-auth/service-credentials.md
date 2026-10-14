# Service-to-Service Credentials

### Each service has its own credential, and the token names the service it is for

**Why:** one static key shared by every caller cannot be rotated without a coordinated deploy or
revoked for one caller alone; a client-credentials token, a workload identity or mutual TLS is per
service. The token's `aud` names the receiving service, which verifies it like any other — a token
minted for one service and replayed against another is rejected. A user's token is not forwarded
across a trust boundary: inside one, the next service verifies it with its own audience in the
list or exchanges it; across one, the call uses the service's own credential. The client secret
comes from the environment or a secret manager.

**Example:**
```python
# WRONG — one shared key for every caller, sent as is
@final
class TimetableClient:
    def __init__(self, *, api: TimetableApi, shared_api_key: str) -> None:
        self._api = api
        self._shared_api_key = shared_api_key

    async def lessons_for(self, form_group_id: FormGroupId) -> tuple[Lesson, ...]:
        headers = {"X-Api-Key": self._shared_api_key}
        return await self._api.get_lessons(form_group_id, headers=headers)


# CORRECT — this service's own token, minted for the timetable audience
@final
class TimetableClient:
    def __init__(
        self, *, api: TimetableApi, tokens: OutboundTokens, audience: str = _TIMETABLE_AUDIENCE
    ) -> None:
        self._api = api
        self._tokens = tokens
        self._audience = audience

    async def lessons_for(self, form_group_id: FormGroupId) -> tuple[Lesson, ...]:
        token = await self._tokens.token_for(audience=self._audience)
        headers = {"Authorization": f"Bearer {token}"}
        return await self._api.get_lessons(form_group_id, headers=headers)
```

### An outbound token is fetched once and reused until shortly before its `exp`

**Why:** fetched per request, every call pays a round trip to the identity provider and its rate
limit; cached past its `exp`, every call fails. The client object the root owns keeps it, and
renews a safety margin before expiry.
