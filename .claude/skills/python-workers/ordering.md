# Ordering

Two consumers, a prefetch window, a redelivery behind newer messages or a retry republished at the
tail each reorder a queue. Either the handler does not care, or the order is bought explicitly.

### A handler that needs order skips an event older than the state it already holds

**Why:** an older event applied after a newer one rolls the state back — a cancellation overwritten
by the confirmation it cancelled. The payload carries the aggregate's version, and the handler
compares it with the stored one — the version column from `python-persistence`.
**Except:** order bought by partitioning — a Kafka record's key picks its partition and one
consumer handles it in order; RabbitMQ's `x-single-active-consumer` gives a queue one consumer at a
time. Either way, order holds only while one message per key is in flight; concurrency inside the
consumer undoes it.

**Example:**
```python
# WRONG — the last event to arrive wins, whichever was published last
async def apply_booking_status(event: BookingStatusChanged, *, bookings: Bookings) -> None:
    await bookings.set_status(event.booking_id, event.status)


# CORRECT — an event older than the stored version is skipped
async def apply_booking_status(event: BookingStatusChanged, *, bookings: Bookings) -> None:
    current_version = await bookings.version_of(event.booking_id)
    if event.version <= current_version:
        return
    await bookings.set_status(event.booking_id, event.status, version=event.version)
```
