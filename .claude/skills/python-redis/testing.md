# Testing Against redis

### Tests run against a real redis from testcontainers, on the client the root builds

**Why:** only a real server shows `ex` truncation, a refused write or a dropped subscription. The
container is `testcontainers.community.redis.RedisContainer("redis:8")` — the module
`testcontainers.redis` is deprecated, and with warnings as errors importing it fails the run — and
each test starts from `flushdb()` on a client built by the same function the root uses, so the
tests exercise the production timeouts and retry.

**Example:**
```python
# WRONG — a client built differently from production: the constructor's ten retries hide drops
@pytest.fixture
async def occupancy_client(redis_container: RedisContainer) -> AsyncIterator[Redis]:
    async with Redis(
        host=redis_container.get_container_host_ip(), port=redis_container.port
    ) as client:
        yield client


# CORRECT — the root's own builder, a clean database per test, the client closed after
@pytest.fixture
async def occupancy_client(redis_url: str) -> AsyncIterator[Redis]:
    async with build_occupancy_client(url=redis_url) as client:
        await client.flushdb()
        yield client
```

### The loss test kills the subscription from a second client, for both kinds of client

**Why:** a client from the constructor resubscribes silently and one from `from_url` raises, so
the channel must catch both, and only a test of each shows it does.
`await admin.client_kill_filter(_type="pubsub")` drops every subscriber; the next `anext` raises
`BayChangesLostError`.

**Example:**
```python
# WRONG — only the happy path: a silent resubscribe after a drop passes unnoticed
async def test_published_change_is_received(channel: RedisBayChangeChannel) -> None:
    async with channel.subscribe() as changes:
        await channel.publish(_BAY_TAKEN)

        received = await anext(changes)

    assert received == _BAY_TAKEN


# CORRECT — the subscription is killed, and the next read raises the channel's error
async def test_killed_subscription_raises_lost(
    channel: RedisBayChangeChannel, admin: Redis
) -> None:
    async with channel.subscribe() as changes:
        await admin.client_kill_filter(_type="pubsub")

        with pytest.raises(BayChangesLostError):
            async with asyncio.timeout(_DELIVERY_TIMEOUT_SECONDS):
                await anext(changes)
```

### A cache in redis has one test of its own: no key it writes lives forever

**Why:** a TTL lost on the way — an `ex` that became zero and was refused, an option dropped —
leaves a key that never expires; `ttl` answers `-1` for one, so the test asserts every TTL is
positive, never only that one exists.
