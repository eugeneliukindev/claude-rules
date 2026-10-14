# Testing a Worker

### A handler's unit test calls it with a body and a fake, and a redelivery is a second call

**Why:** the handler is a plain function, so its tests need no broker. The fake inherits the
contract, lives in `tests/fakes.py` and passes the same contract suite as the real implementation —
here, that a repeated idempotency key submits the print job once.

**Example:**
```python
# WRONG — one delivery, so a handler that prints the enlargement twice on redelivery passes
async def test_on_enlargement_requested_submits_print_job() -> None:
    print_station = InMemoryPrintStation()
    request = make_enlargement_requested_v1()

    await on_enlargement_requested(request.to_json(), print_station=print_station)

    assert print_station.submitted_scan_ids == [ScanId(request.scan_id)]


# CORRECT — tests/fakes.py, and the redelivery is the second call
@final
class InMemoryPrintStation(PrintStation):
    def __init__(self) -> None:
        self.submitted_scan_ids: list[ScanId] = []
        self._idempotency_keys: set[str] = set()

    @override
    async def submit(self, scan_id: ScanId, *, idempotency_key: str) -> None:
        if idempotency_key in self._idempotency_keys:
            return
        self._idempotency_keys.add(idempotency_key)
        self.submitted_scan_ids.append(scan_id)


async def test_on_enlargement_requested_redelivered_request_prints_once() -> None:
    print_station = InMemoryPrintStation()
    request = make_enlargement_requested_v1()
    body = request.to_json()

    await on_enlargement_requested(body, print_station=print_station)
    await on_enlargement_requested(body, print_station=print_station)

    assert print_station.submitted_scan_ids == [ScanId(request.scan_id)]
```

### Each queue has one test on the real broker that a rejected message is dead-lettered

**Why:** acknowledgement, the delivery limit and dead-lettering exist only in the broker; a unit
test that the handler raises, or an in-memory test broker that runs it inline, passes on a queue
that drops every failing message. The test publishes a message the handler rejects and reads it back
from the dead-letter queue.

**Example:**
```python
# WRONG — proves the handler raises, not that the broker keeps the message
async def test_malformed_enlargement_request_is_dead_lettered() -> None:
    with pytest.raises(ValidationError):
        await on_enlargement_requested(b'{"version": 1}', print_station=InMemoryPrintStation())


# CORRECT — the real broker applies the queue's arguments and moves the message
@pytest.mark.integration
async def test_malformed_enlargement_request_is_dead_lettered(
    lab_broker: LabBrokerHarness,
) -> None:
    await lab_broker.publish(b'{"version": 1}', _ENLARGEMENTS_QUEUE_NAME)

    dead_lettered = await lab_broker.next_dead_letter(_ENLARGEMENTS_QUEUE_NAME, timeout_seconds=5.0)

    assert dead_lettered.body == b'{"version": 1}'
```
