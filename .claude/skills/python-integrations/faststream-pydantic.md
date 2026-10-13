# FastStream and pydantic

The seam between `python-faststream` and `python-pydantic`, linked from both skills.

### The subscriber takes the raw message, and the handler validates its body as JSON

**Why:** an annotated message parameter is validated against the dict FastStream already decoded, in
Python mode, so a strict model rejects every UUID, `Decimal` and datetime in every valid message —
measured: the UUID arrives as a `str`, `is_instance_of` fails, and nothing is handled. With the raw
message, `model_validate_json` runs in JSON mode; a failed validation escapes, and `REJECT_ON_ERROR`
dead-letters the message on its first delivery (measured).

**Example:**
```python
# WRONG — validated in Python mode: the UUID arrives as a str, and every message fails
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: BookingConfirmedV1) -> None:
    await hold_room(message.to_domain(), inventory=inventory)


# CORRECT — the raw body reaches the handler, which validates it in JSON mode
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    await on_booking_confirmed(message.body, inventory=inventory)
```
