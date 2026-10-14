# Pub/Sub: `RedisBayChangeChannel`

## Contents

- A second subscribe confirmation is a gap
- A `ConnectionError` while listening is a gap too
- The subscription is live before `subscribe` yields
- What is not a gap, and what redis drops

Pub/sub delivers to whoever listens at that moment and keeps nothing, so a subscriber that was
disconnected has missed events and must say so. The channel here carries bay changes of a car park
and promises that **a subscription that may have missed an event raises `BayChangesLostError`
while iterating** — not only on leaving the `async with`, where a loop reading it would never see
it — so the reader can reload the occupancy from the database. The payload is the application's
own — `encode_bay_change` and `decode_bay_change`, versioned, raising `UndecodableBayChangeError`
for one they refuse — so the channel carries bytes and knows no schema. `RedisConnectionError` is
`redis.exceptions.ConnectionError`, imported under that name so it does not shadow the builtin.

**What a dropped connection looks like depends on how the client was built** (*measured*, with
`CLIENT KILL TYPE pubsub` from a second client). Through the constructor's retry,
`pubsub.listen()` reconnects and resubscribes without raising: an event published in between is
never delivered, and the only sign is a second `subscribe` confirmation. Through `from_url`, or
with `retries=0`, `listen()` raises `ConnectionError`.

### A second `subscribe` confirmation is a gap, raised as the channel's error

**Why:** after a silent resubscribe the only trace of the drop is the confirmation; read past, the
reader follows a subscription that missed events and shows a stale count forever.

**Example:**
```python
# WRONG — only messages are read: after a silent resubscribe nobody learns what was missed
async def _decode_bay_changes(messages: AsyncIterator[Any]) -> AsyncIterator[BayChange]:
    async for received in messages:
        match received:
            case {"type": "message", "data": bytes() as payload}:
                yield decode_bay_change(payload)
            case _:
                continue  # unsubscribe confirmations and pattern messages carry no change


# CORRECT — a second confirmation is a gap, and the channel says so
async def _decode_bay_changes(messages: AsyncIterator[Any]) -> AsyncIterator[BayChange]:
    async for received in messages:
        match received:
            case {"type": "subscribe"}:
                raise BayChangesLostError(_BAY_CHANGES_CHANNEL)
            case {"type": "message", "data": bytes() as payload}:
                yield decode_bay_change(payload)
            case _:
                continue  # unsubscribe confirmations and pattern messages carry no change
```

### A `ConnectionError` while listening is the channel's error too, and a bad payload is skipped

**Why:** a client without retries raises instead of resubscribing; uncaught, the redis error
escapes a reader that only catches the channel's. A payload that fails to decode is logged and
skipped — it is one bad message, never a reason to drop the subscription — and the decoder ignores
fields a newer publisher adds.

**Example:**
```python
# WRONG — the redis error escapes, and one malformed payload ends the subscription
async def _decode_bay_changes(messages: AsyncIterator[Any]) -> AsyncIterator[BayChange]:
    async for received in messages:
        match received:
            case {"type": "subscribe"}:
                raise BayChangesLostError(_BAY_CHANGES_CHANNEL)
            case {"type": "message", "data": bytes() as payload}:
                yield decode_bay_change(payload)
            case _:
                continue  # unsubscribe confirmations and pattern messages carry no change


# CORRECT — both kinds of gap are the channel's error; a bad payload is logged and skipped
async def _decode_bay_changes(messages: AsyncIterator[Any]) -> AsyncIterator[BayChange]:
    try:
        async for received in messages:
            match received:
                case {"type": "subscribe"}:
                    raise BayChangesLostError(_BAY_CHANGES_CHANNEL)
                case {"type": "message", "data": bytes() as payload}:
                    try:
                        change = decode_bay_change(payload)
                    except UndecodableBayChangeError:
                        logger.warning("bay change dropped", extra={"payload_size": len(payload)})
                        continue
                    yield change
                case _:
                    continue  # unsubscribe confirmations and pattern messages carry no change
    except RedisConnectionError as error:
        raise BayChangesLostError(_BAY_CHANGES_CHANNEL) from error
```

### `subscribe` reads the first confirmation before it yields

**Why:** the reader reloads the occupancy once the subscription is live; yielded before the
confirmation, a change published in that moment is in neither the reload nor the subscription.

**Example:**
```python
# WRONG — yields before redis has confirmed: "live" is a guess
@final
class RedisBayChangeChannel:
    def __init__(self, *, client: Redis) -> None:
        self._client = client

    async def publish(self, change: BayChange) -> None:
        await self._client.publish(_BAY_CHANGES_CHANNEL, encode_bay_change(change))

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[BayChange]]:
        async with self._client.pubsub() as pubsub:
            await pubsub.subscribe(_BAY_CHANGES_CHANNEL)
            yield _decode_bay_changes(pubsub.listen())


# CORRECT — the confirmation is read first, and a failure to subscribe is the channel's error
@final
class RedisBayChangeChannel:
    def __init__(self, *, client: Redis) -> None:
        self._client = client

    async def publish(self, change: BayChange) -> None:
        await self._client.publish(_BAY_CHANGES_CHANNEL, encode_bay_change(change))

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[BayChange]]:
        async with self._client.pubsub() as pubsub:
            messages = pubsub.listen()
            try:
                await pubsub.subscribe(_BAY_CHANGES_CHANNEL)
                await anext(messages)  # the confirmation: the subscription is live from here
            except RedisConnectionError as error:
                raise BayChangesLostError(_BAY_CHANGES_CHANNEL) from error
            yield _decode_bay_changes(messages)
```

## What Is Not a Gap, and What redis Drops

- **A subscription idle past `socket_timeout` is not a gap**: *measured*, `listen()` kept waiting
  through three times a 0.3-second timeout and then delivered, so the process's one client, with
  its short timeouts, serves the subscription too.
- **redis drops a subscriber that stops reading**: the default `client-output-buffer-limit pubsub
  32mb 8mb 60` disconnects one whose unread output passes 32 MiB, or 8 MiB for a minute — which
  the channel reports as a gap. A reader that never blocks on anything else keeps it reading.
