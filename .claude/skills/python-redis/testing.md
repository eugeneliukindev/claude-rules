# Testing Against redis

The contract suites are in `python-caching` and `python-streaming`; the container fixture's
mechanics are `python-pytest`.

### Both implementations join their contract suites against a real redis from testcontainers

**Why:** the fake passes the suite by construction; only a real server shows `ex` truncation, a
refused write or a dropped subscription. The container is
`testcontainers.community.redis.RedisContainer("redis:8")` — the module `testcontainers.redis` is
deprecated, and with warnings as errors importing it fails the run — and each test starts from
`flushdb()` on a client built by the same `managed_redis` the root uses, so the tests exercise the
production timeouts and retry.

**Example:**
```python
# WRONG — a client built differently from production: the constructor's ten retries hide drops
@pytest.fixture
async def redis_cache(redis_container: RedisContainer) -> AsyncIterator[Cache]:
    client = Redis(host=redis_container.get_container_host_ip(), port=redis_container.port)
    yield RedisCache(client)


# CORRECT — the root's own builder, a clean database per test, the client closed after
@pytest.fixture
async def redis_cache(redis_url: str) -> AsyncIterator[Cache]:
    async with managed_redis(url=redis_url, timeout_seconds=_TIMEOUT_SECONDS) as client:
        await client.flushdb()
        yield RedisCache(client)
```

### The loss test kills the subscription from a second client, for both kinds of client

**Why:** a client from the constructor resubscribes silently and one from `from_url` raises, so
the implementation must catch both, and only a test of each shows it does.
`await admin.client_kill_filter(_type="pubsub")` drops every subscriber; the next `anext` raises
`ParcelEventChannelLostError`.

**Example:**
```python
# WRONG — only the happy path: a silent resubscribe after a drop passes unnoticed
async def test_published_event_is_received(channel: ParcelEventChannel) -> None:
    async with channel.subscribe() as events:
        await channel.publish(_OUT_FOR_DELIVERY)

        received = await anext(events)

    assert received == _OUT_FOR_DELIVERY


# CORRECT — the subscription is killed, and the next read raises the contract's error
async def test_killed_subscription_raises_lost(channel: ParcelEventChannel, admin: Redis) -> None:
    async with channel.subscribe() as events:
        await admin.client_kill_filter(_type="pubsub")

        with pytest.raises(ParcelEventChannelLostError):
            async with asyncio.timeout(_DELIVERY_TIMEOUT_SECONDS):
                await anext(events)
```

### `RedisCache` has one test of its own: no key it writes lives forever

**Why:** a TTL lost on the way — an `ex` that became zero and was refused, an option dropped —
leaves a key that never expires; `ttl` answers `-1` for one, so the test asserts every TTL is
positive, never only that one exists.
