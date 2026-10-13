# Subscriptions

A subscription gets a bounded queue per subscriber, releases what it holds on disconnect, ends after
a maximum lifetime, fans out between workers through a channel contract, and checks `Origin` (why
and how: `python-streaming`). Strawberry's part is below.

### A subscription is an async generator that releases what it holds, through `aclosing`

**Why:** on the client's `complete` or a disconnect strawberry closes the generator, and its
`finally` runs; a generator it iterates is closed only if it is entered with `aclosing`
(`python-async`) — measured, both released. Exception handlers do not apply to subscription fields:
an exception out of the generator is sent as one `errors` payload, masked like any other, followed
by `complete` — the subscription is over, and the client subscribes again.

**Example:**
```python
# WRONG — on disconnect this generator is closed, but the feed's generator is left suspended
@strawberry.type
class Subscription:
    @strawberry.subscription
    async def claim_status(
        self, info: GraphQLInfo, claim_id: UUID
    ) -> AsyncGenerator[ClaimStatusChanged]:
        events = follow_claim(
            ClaimId(claim_id), feed=info.context.claim_feed, lifetime_seconds=_LIFETIME_SECONDS
        )
        async for event in events:
            yield ClaimStatusChanged.from_domain(event)


# CORRECT — aclosing closes the feed's generator however the subscription ends
@strawberry.type
class Subscription:
    @strawberry.subscription
    async def claim_status(
        self, info: GraphQLInfo, claim_id: UUID
    ) -> AsyncGenerator[ClaimStatusChanged]:
        events = follow_claim(
            ClaimId(claim_id), feed=info.context.claim_feed, lifetime_seconds=_LIFETIME_SECONDS
        )
        async with aclosing(events) as claim_events:
            async for event in claim_events:
                yield ClaimStatusChanged.from_domain(event)
```

### The router speaks one protocol, `graphql-transport-ws`

**Why:** the default also accepts the legacy `graphql-ws`, a second protocol to keep working and to
test. Excluded, a client asking for it is refused with 4406.

### The per-connection limits are set to what a client needs

**Why:** `max_subscriptions_per_connection` is 100 by default and `connection_init_wait_timeout` a
minute: one connection can hold a hundred subscriptions, and a socket that never sends
`connection_init` holds a slot for a minute.
