# Testing FastStream

The handler's own tests call the plain function with a fake and need no broker. FastStream adds two
levels above it.

### `TestRabbitBroker` checks the wiring, and nothing the broker does

**Why:** it runs the subscriber inline: it checks the router's wiring, the routing key and that a
valid message reaches the handler, and raises the handler's exception into the test. It has no
acknowledgement, no delivery limit and no dead-letter exchange, so a test of those through it
passes on a configuration that drops every failing message.

**Example:**
```python
# WRONG — asserts a dead-letter path the in-memory broker does not have
async def test_telemetry_router_malformed_fault_is_dead_lettered() -> None:
    broker = RabbitBroker()
    broker.include_router(build_telemetry_router(scheduler=RecordingInspectionScheduler()))

    async with TestRabbitBroker(broker) as in_memory_broker:
        with pytest.raises(ValidationError):
            await in_memory_broker.publish({"version": 99}, _DOOR_FAULTS_QUEUE_NAME)


# CORRECT — the wiring: a valid fault reaches the handler and books an inspection
async def test_telemetry_router_door_fault_schedules_inspection() -> None:
    scheduler = RecordingInspectionScheduler()
    broker = RabbitBroker()
    broker.include_router(build_telemetry_router(scheduler=scheduler))
    fault = build_door_fault_v1()

    async with TestRabbitBroker(broker) as in_memory_broker:
        await in_memory_broker.publish(fault.to_json(), _DOOR_FAULTS_QUEUE_NAME)

    assert scheduler.inspected_car_ids == [CarId(fault.car_id)]
```

### A dead-letter test publishes to a real RabbitMQ and reads the message back with `get_one`

**Why:** acknowledgement, the delivery limit and dead-lettering exist only in the broker, so the
test runs against one — `RabbitMqContainer` from `testcontainers.community.rabbitmq`. A subscriber
with no handler, declared on the dead-letter queue, is read with `get_one(timeout=...)` after
`broker.start()`; a test that only publishes passes whether the message was dead-lettered or
dropped.

**Example:**
```python
# WRONG — the message is published and nothing is read back: a drop and a dead-letter both pass
async def test_telemetry_router_malformed_fault_is_dead_lettered(amqp_url: str) -> None:
    broker = RabbitBroker(amqp_url)
    broker.include_router(build_telemetry_router(scheduler=RecordingInspectionScheduler()))

    async with broker:
        await broker.start()
        await broker.publish({"version": 99}, _DOOR_FAULTS_QUEUE_NAME)


# CORRECT — the rejected message is read back from the dead-letter queue
async def test_telemetry_router_malformed_fault_is_dead_lettered(amqp_url: str) -> None:
    broker = RabbitBroker(amqp_url)
    broker.include_router(build_telemetry_router(scheduler=RecordingInspectionScheduler()))
    dead_letters = broker.subscriber(
        RabbitQueue(_DOOR_FAULTS_DEAD_LETTER_QUEUE_NAME, queue_type=QueueType.QUORUM)
    )

    async with broker:
        await broker.start()
        await broker.publish({"version": 99}, _DOOR_FAULTS_QUEUE_NAME)
        dead_letter = await dead_letters.get_one(timeout=_DEAD_LETTER_WAIT_SECONDS)

    assert dead_letter is not None
```
