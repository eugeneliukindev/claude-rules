# Pub/Sub: `RedisParcelEventChannel`

## Contents

- A second subscribe confirmation is a gap
- A `ConnectionError` while listening is a gap too
- The subscription is live before `subscribe` yields
- What is not a gap, and what redis drops
- The wire model and the root that builds the channel

The channel contract, the relay and the fake are in `python-streaming`; the contract's promise is
that **a subscription that may have missed an event raises `ParcelEventChannelLostError` while
iterating** — not only on leaving the `async with`, where the relay's loop would never see it.
`RedisConnectionError` is `redis.exceptions.ConnectionError`, imported under that name so it does
not shadow the builtin. The wire model's settings are `python-pydantic`.

**What a dropped connection looks like depends on how the client was built** (*measured*, with
`CLIENT KILL TYPE pubsub` from a second client). Through the constructor's retry,
`pubsub.listen()` reconnects and resubscribes without raising: an event published in between is
never delivered, and the only sign is a second `subscribe` confirmation. Through `from_url`, or
with `retries=0`, `listen()` raises `ConnectionError`.

### A second `subscribe` confirmation is a gap, raised as the contract's error

**Why:** after a silent resubscribe the only trace of the drop is the confirmation; read past, the
relay follows a subscription that missed events and never ends the streams that depend on it.

**Example:**
```python
# WRONG — only messages are read: after a silent resubscribe nobody learns what was missed
async def _decode_events(messages: AsyncIterator[Any]) -> AsyncIterator[ParcelEvent]:
    async for received in messages:
        match received:
            case {"type": "message", "data": bytes() as payload}:
                yield _ParcelEventMessage.model_validate_json(payload).to_domain()
            case _:
                continue  # unsubscribe confirmations and pattern messages carry no event


# CORRECT — a second confirmation is a gap, and the contract says so
async def _decode_events(messages: AsyncIterator[Any]) -> AsyncIterator[ParcelEvent]:
    async for received in messages:
        match received:
            case {"type": "subscribe"}:
                raise ParcelEventChannelLostError(_PARCEL_EVENTS_CHANNEL)
            case {"type": "message", "data": bytes() as payload}:
                yield _ParcelEventMessage.model_validate_json(payload).to_domain()
            case _:
                continue  # unsubscribe confirmations and pattern messages carry no event
```

### A `ConnectionError` while listening is the contract's error too, and a bad payload is skipped

**Why:** a client without retries raises instead of resubscribing; uncaught, the redis error
escapes a relay that only catches the contract's. A payload that fails validation is logged and
skipped — it is one bad message, never a reason to drop the subscription — and the wire model is a
queued payload, so it ignores fields a newer worker adds.

**Example:**
```python
# WRONG — the redis error escapes, and one malformed payload ends the subscription
async def _decode_events(messages: AsyncIterator[Any]) -> AsyncIterator[ParcelEvent]:
    async for received in messages:
        match received:
            case {"type": "subscribe"}:
                raise ParcelEventChannelLostError(_PARCEL_EVENTS_CHANNEL)
            case {"type": "message", "data": bytes() as payload}:
                yield _ParcelEventMessage.model_validate_json(payload).to_domain()
            case _:
                continue  # unsubscribe confirmations and pattern messages carry no event


# CORRECT — both kinds of gap are the contract's error; a bad payload is counted and skipped
async def _decode_events(messages: AsyncIterator[Any]) -> AsyncIterator[ParcelEvent]:
    try:
        async for received in messages:
            match received:
                case {"type": "subscribe"}:
                    raise ParcelEventChannelLostError(_PARCEL_EVENTS_CHANNEL)
                case {"type": "message", "data": bytes() as payload}:
                    try:
                        decoded = _ParcelEventMessage.model_validate_json(payload)
                    except ValidationError:
                        logger.warning("parcel event dropped", extra={"payload_size": len(payload)})
                        continue
                    yield decoded.to_domain()
                case _:
                    continue  # unsubscribe confirmations and pattern messages carry no event
    except RedisConnectionError as error:
        raise ParcelEventChannelLostError(_PARCEL_EVENTS_CHANNEL) from error
```

### `subscribe` reads the first confirmation before it yields

**Why:** the relay ends its streams once the subscription is live (`python-streaming`); yielded
before the confirmation, an event published in that moment is lost after the streams were already
told to resume.

**Example:**
```python
# WRONG — yields before redis has confirmed: "live" is a guess
@final
class RedisParcelEventChannel(ParcelEventChannel):
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    @override
    async def publish(self, event: ParcelEvent) -> None:
        message = _ParcelEventMessage.from_domain(event)
        await self._redis.publish(_PARCEL_EVENTS_CHANNEL, message.model_dump_json())

    @override
    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[ParcelEvent]]:
        async with self._redis.pubsub() as pubsub:
            await pubsub.subscribe(_PARCEL_EVENTS_CHANNEL)
            yield _decode_events(pubsub.listen())


# CORRECT — the confirmation is read first, and a failure to subscribe is the contract's error
@final
class RedisParcelEventChannel(ParcelEventChannel):
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    @override
    async def publish(self, event: ParcelEvent) -> None:
        message = _ParcelEventMessage.from_domain(event)
        await self._redis.publish(_PARCEL_EVENTS_CHANNEL, message.model_dump_json())

    @override
    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[ParcelEvent]]:
        async with self._redis.pubsub() as pubsub:
            messages = pubsub.listen()
            try:
                await pubsub.subscribe(_PARCEL_EVENTS_CHANNEL)
                await anext(messages)  # the confirmation: the subscription is live from here
            except RedisConnectionError as error:
                raise ParcelEventChannelLostError(_PARCEL_EVENTS_CHANNEL) from error
            yield _decode_events(messages)
```

## What Is Not a Gap, and What redis Drops

- **A subscription idle past `socket_timeout` is not a gap**: *measured*, `listen()` kept waiting
  through three times a 0.3-second timeout and then delivered, so the root's shared client, with
  its short cache timeouts, serves the subscription too.
- **redis drops a subscriber that stops reading**: the default `client-output-buffer-limit pubsub
  32mb 8mb 60` disconnects one whose unread output passes 32 MiB, or 8 MiB for a minute — which
  the implementation reports as a gap. A relay that never awaits a socket keeps it reading.

## The Wire Model and the Root

In `parcel_events/redis_pubsub.py`, named for its mechanism — a Redis Streams implementation, which
would also replay what a dropped subscriber missed, is a second file beside it:

```python
@final
class _ParcelEventMessage(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    version: Literal[1] = 1
    tracking_number: str
    sequence: int
    status: ParcelStatus

    @classmethod
    def from_domain(cls, event: ParcelEvent) -> Self:
        return cls(
            tracking_number=event.tracking_number, sequence=event.sequence, status=event.status
        )

    def to_domain(self) -> ParcelEvent:
        return ParcelEvent(
            tracking_number=TrackingNumber(self.tracking_number),
            sequence=self.sequence,
            status=self.status,
        )
```

`RedisParcelEventChannel` and `_decode_events` are the last `CORRECT`s above. The composition root
builds the client once and both implementations on it, runs the relay in its task group and cancels
it at shutdown — in a FastAPI service that root is the lifespan:

```python
@asynccontextmanager
async def tracking_resources(settings: TrackingSettings) -> AsyncIterator[TrackingResources]:
    async with (
        managed_redis(
            url=settings.redis_url, timeout_seconds=settings.redis_timeout_seconds
        ) as redis,
        asyncio.TaskGroup() as tasks,
    ):
        feed = ParcelFeed()
        parcel_events = RedisParcelEventChannel(redis=redis)
        relay = tasks.create_task(ParcelEventRelay(channel=parcel_events, feed=feed).run())
        yield TrackingResources(cache=RedisCache(redis), feed=feed, parcel_events=parcel_events)
        relay.cancel()
```
