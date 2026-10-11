# Testing FastStream

The handler's unit tests call the plain function with a fake (`python-workers`). FastStream adds two
levels above it.

### `TestRabbitBroker` checks the wiring, and nothing the broker does

**Why:** it runs the subscriber inline: it checks the router's wiring, the routing key and that a
valid message reaches the handler, and raises the handler's exception into the test. It has no
acknowledgement, no delivery limit and no dead-letter exchange, so a test of those through it
passes on a configuration that drops every failing message.

**Example:**
```python
# WRONG — asserts a dead-letter path the in-memory broker does not have
async def test_booking_router_malformed_message_is_dead_lettered() -> None:
    broker = RabbitBroker()
    broker.include_router(build_booking_router(inventory=InMemoryRoomInventory()))

    async with TestRabbitBroker(broker) as test_broker:
        with pytest.raises(ValidationError):
            await test_broker.publish({"version": 99}, _BOOKINGS_QUEUE_NAME)


# CORRECT — the wiring: a valid message reaches the handler and holds the room
async def test_booking_router_valid_message_holds_room() -> None:
    inventory = InMemoryRoomInventory()
    broker = RabbitBroker()
    broker.include_router(build_booking_router(inventory=inventory))
    message = make_booking_confirmed_v1()

    async with TestRabbitBroker(broker) as test_broker:
        await test_broker.publish(message.model_dump(mode="json"), _BOOKINGS_QUEUE_NAME)

    assert inventory.held_booking_ids == [BookingId(message.booking_id)]
```

### Each queue has one test against a real RabbitMQ that a rejected message is dead-lettered

**Why:** acknowledgement, the delivery limit and dead-lettering exist only in the broker.
`RabbitMqContainer` from `testcontainers.community.rabbitmq` (`python-pytest`) provides it; the
test publishes a message the handler rejects and reads it back from the dead-letter queue, which a
subscriber on that queue declares.

**Example:**
```python
# WRONG — the message is published and nothing is read back: a drop and a dead-letter both pass
async def test_booking_router_malformed_message_is_dead_lettered(amqp_url: str) -> None:
    broker = RabbitBroker(amqp_url)
    broker.include_router(build_booking_router(inventory=InMemoryRoomInventory()))

    async with broker:
        await broker.start()
        await broker.publish({"version": 99}, _BOOKINGS_QUEUE_NAME)


# CORRECT — the rejected message is read back from the dead-letter queue
async def test_booking_router_malformed_message_is_dead_lettered(amqp_url: str) -> None:
    broker = RabbitBroker(amqp_url)
    broker.include_router(build_booking_router(inventory=InMemoryRoomInventory()))
    dead_letters = broker.subscriber(
        RabbitQueue(_BOOKINGS_DEAD_LETTER_QUEUE_NAME, queue_type=QueueType.QUORUM)
    )

    async with broker:
        await broker.start()
        await broker.publish({"version": 99}, _BOOKINGS_QUEUE_NAME)
        dead_letter = await dead_letters.get_one(timeout=_DEAD_LETTER_WAIT_SECONDS)

    assert dead_letter is not None
```
