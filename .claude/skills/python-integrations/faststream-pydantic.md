# FastStream and pydantic

The seam between `python-faststream` and `python-pydantic`, linked from both skills.

### The subscriber takes the raw message, and the handler validates its body as JSON

**Why:** an annotated message parameter is validated against the dict FastStream already decoded, in
Python mode, so a strict model rejects every UUID, `Decimal` and datetime in every valid message —
measured on FastStream 0.7: the UUID arrives as a `str`, `is_instance_of` fails, and nothing is
handled. With the raw message, `model_validate_json` runs in JSON mode; a failed validation
escapes, and `REJECT_ON_ERROR` dead-letters the message on its first delivery (measured).

**Example:**
```python
# WRONG — validated in Python mode: the UUID arrives as a str, and every delivery fails
def build_harvest_router(*, presses: PressSchedule) -> RabbitRouter:
    router = RabbitRouter()

    @router.subscriber(_GRAPE_DELIVERIES_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
    async def on_grape_delivery_message(message: GrapeDeliveredV1) -> None:
        await presses.schedule_pressing(message.to_domain())

    return router


# CORRECT — the raw body reaches a plain function, which validates it in JSON mode
def build_harvest_router(*, presses: PressSchedule) -> RabbitRouter:
    router = RabbitRouter()

    @router.subscriber(_GRAPE_DELIVERIES_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
    async def on_grape_delivery_message(message: RabbitMessage) -> None:
        await record_grape_delivery(message.body, presses=presses)

    return router


async def record_grape_delivery(body: bytes, /, *, presses: PressSchedule) -> None:
    delivery = GrapeDeliveredV1.model_validate_json(body)
    await presses.schedule_pressing(delivery.to_domain())
```
