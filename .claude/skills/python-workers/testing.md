# Testing a Worker

FastStream's in-memory and real-broker tests are in `python-faststream`.

### A handler's unit test calls it with a body and a fake, and a redelivery is a second call

**Why:** the handler is a plain function, so its tests need no broker. The fake inherits the
contract, lives in `tests/fakes.py` and passes the same contract suite as the real implementation
(`python-contracts`) — here, that a repeated idempotency key holds the room once.

**Example:**
```python
# WRONG — one delivery, so a handler that holds the room twice on redelivery passes
async def test_on_booking_confirmed_holds_room() -> None:
    inventory = InMemoryRoomInventory()
    message = make_booking_confirmed_v1()

    await on_booking_confirmed(message.model_dump_json().encode(), inventory=inventory)

    assert inventory.held_booking_ids == [BookingId(message.booking_id)]


# CORRECT — tests/fakes.py, and the redelivery is the second call
@final
class InMemoryRoomInventory(RoomInventory):
    def __init__(self) -> None:
        self.held_booking_ids: list[BookingId] = []
        self._idempotency_keys: set[str] = set()

    @override
    async def hold(self, booking_id: BookingId, *, idempotency_key: str) -> None:
        if idempotency_key in self._idempotency_keys:
            return
        self._idempotency_keys.add(idempotency_key)
        self.held_booking_ids.append(booking_id)


async def test_on_booking_confirmed_redelivered_message_holds_room_once() -> None:
    inventory = InMemoryRoomInventory()
    message = make_booking_confirmed_v1()
    body = message.model_dump_json().encode()

    await on_booking_confirmed(body, inventory=inventory)
    await on_booking_confirmed(body, inventory=inventory)

    assert inventory.held_booking_ids == [BookingId(message.booking_id)]
```

### Each queue has one test on the real broker that a rejected message is dead-lettered

**Why:** acknowledgement, the delivery limit and dead-lettering exist only in the broker, and an
in-memory test broker that runs the handler inline tests none of them.

**Example:**
```python
# WRONG — the in-memory broker runs the handler inline; no queue argument is ever exercised
async def test_invalid_booking_message_is_rejected(test_broker: TestBroker) -> None:
    with pytest.raises(ValidationError):
        await test_broker.publish(b'{"version": 1}', "bookings.confirmed")


# CORRECT — the real broker applies the queue's arguments and moves the message
@pytest.mark.integration
async def test_invalid_booking_message_reaches_dead_letter_queue(rabbit: RabbitTestEnv) -> None:
    await rabbit.publish(b'{"version": 1}', "bookings.confirmed")

    dead_lettered = await rabbit.next_message("bookings.confirmed.dead", timeout_seconds=5.0)

    assert dead_lettered.body == b'{"version": 1}'
```
