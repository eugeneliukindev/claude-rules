---
name: python-boundaries
description: >-
  Designs what crosses a process boundary: validation at the edge, timeouts, retries, idempotency,
  serialization, files other processes read, time, money, identifiers. ALWAYS invoke this skill when
  code calls HTTP, a queue, a cache or a database, writes a file or payload another process reads,
  or handles datetimes, Decimal amounts or UUIDs. Do not write boundary code directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Boundaries

The design, whatever library carries it; a library's own API and traps come from its current
documentation.

## Boundary Models and Domain Objects

### Validating models live at the process boundary; frozen dataclasses live inside

**Why:** a validating model - a request or response, a message payload, settings, a row from an
untrusted source - is the only place external data is parsed; domain code never imports the
validation library. The edge validates once and passes a domain object inward, so a check repeated
in a service means the boundary leaked. Boundary models are strict: no `"1"` coerced to `1`, no
unknown field dropped. A bare collection is validated through one adapter built once -
constructing the validator is the cost.

**Example:**
```python
# WRONG - the planner takes the request model and re-checks what the boundary should have
@final
class BerthPlanner:
    def __init__(self, *, allocations: BerthAllocations) -> None:
        self._allocations = allocations

    def allocate(self, request: BerthAllocationRequest) -> AllocationId:
        if request.departs_at <= request.arrives_at:
            raise EmptyBerthWindowError(request.arrives_at, request.departs_at)
        return self._allocations.add(request.to_domain())

# CORRECT - the edge parsed and converted; BerthWindow refuses an empty window when it is built
@final
class BerthPlanner:
    def __init__(self, *, allocations: BerthAllocations) -> None:
        self._allocations = allocations

    def allocate(self, allocation: BerthAllocation) -> AllocationId:
        return self._allocations.add(allocation)
```

### The two families are mapped field by field - a plain copy as a method on the schema, a mapping with rules as a function beside it

**Why:** a splat is typed `Any`, so a field renamed on either side passes the type check and fails
in production; named fields fail the check on the line that maps them. Once the view hides a field
by permission, converts a currency or computes a total, a schema that maps itself answers to two
actors - the API's shape and the view's rules - so that mapping moves to a function in the same
boundary module, and the schema stays a shape.

**Example:**
```python
# WRONG - the response model owns who may see the master's phone number
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class VesselResponse:
    name: str
    flag_state: str
    master_phone: str | None

    @classmethod
    def from_domain(cls, vessel: Vessel, *, viewer: HarbourViewer) -> Self:
        is_visible = viewer.operator_id == vessel.operator_id or viewer.is_harbour_master
        return cls(
            name=vessel.name,
            flag_state=vessel.flag_state,
            master_phone=vessel.master_phone if is_visible else None,
        )

# CORRECT - the shape stays a shape; the view's rule is a function beside it
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class VesselResponse:
    name: str
    flag_state: str
    master_phone: str | None

def vessel_response(vessel: Vessel, *, viewer: HarbourViewer) -> VesselResponse:
    is_visible = viewer.operator_id == vessel.operator_id or viewer.is_harbour_master
    return VesselResponse(
        name=vessel.name,
        flag_state=vessel.flag_state,
        master_phone=vessel.master_phone if is_visible else None,
    )
```

### What leaves the process names every field it publishes

**Why:** what a serializer can reach, it will publish - a password hash today, every field added
tomorrow. Over-exposure is a security bug, not a formatting one, so the boundary builds its output
from the domain object field by field and never serializes a domain or ORM object, `__dict__` or
`vars()` by accident.

## External Calls

### Every call that leaves the process has an explicit timeout

**Why:** HTTP, a database, a queue, a cache, DNS - a call with no timeout turns a dependency's
outage into your own: a server that accepts the connection and never answers holds the worker
forever. Client defaults are set once where the client is built; a call overrides them only with a
named constant.

### Only a transient failure is retried, and the adapter classifies it

**Why:** a timeout, a rate limit, a 5xx, a broker disconnect pass with time; a business rejection,
a validation error or an auth failure does not. The adapter translates upstream errors
(`errors.md`) into a transient and a permanent type, and the retry policy - bounded, jittered
backoff, numbers named in the adapter - keys on the type; a pool whose timeout escaped
untranslated broke every caller catching the documented one.
**Except:** a cache read is never retried - the source is its fallback.

**Example:**
```python
# WRONG - one error type for every status, so the policy retries a 404 like a 503
def _raise_for_tide_status(status_code: int, harbour: HarbourCode) -> None:
    if status_code >= HTTPStatus.BAD_REQUEST:
        raise TideServiceError(f"tides for {harbour}: service answered {status_code}")

# CORRECT - classified once, here; the retry policy keys on TransientTideError alone
_RETRYABLE_TIDE_STATUSES: Final = frozenset(
    {
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)

def _raise_for_tide_status(
    status_code: int,
    harbour: HarbourCode,
    *,
    retryable_statuses: frozenset[int] = _RETRYABLE_TIDE_STATUSES,
) -> None:
    if status_code in retryable_statuses:
        raise TransientTideError(f"tides for {harbour}: service answered {status_code}")
    if status_code >= HTTPStatus.BAD_REQUEST:
        raise PermanentTideError(f"tides for {harbour}: service answered {status_code}")
```

### Retries live at one level, the adapter, and the outermost boundary owns the deadline

**Why:** budgets nest multiplicatively - four attempts under a caller making four is sixteen, and
a five-second budget becomes eighty - so a service sees one call that succeeded or failed for
good; a client's built-in retry policy, if any, is that level. A dependency that keeps failing is
no longer called; the adapter raises an unavailability error, so callers degrade, not queue
timeouts.
**Except:** a deadlock or serialization failure is retried above the adapter, by rerunning the
transaction.

### A write is retried only with an idempotency key the operation minted before its first attempt

**Why:** a client that times out after the server committed, and retries with a fresh key, levies
the operator twice. Where the API takes no key, the operation is made idempotent on your side, or
it is not retried.

**Example:**
```python
# WRONG - every attempt mints a new key, so the port authority sees three different levies
@_RETRY_LEVY
async def _levy_harbour_fee(fee: HarbourFee, *, port_billing: PortBilling) -> LevyConfirmation:
    return await port_billing.levy(fee.amount, idempotency_key=str(uuid.uuid4()))

# CORRECT - the fee's own id, minted when the fee was assessed, is the key
@_RETRY_LEVY
async def _levy_harbour_fee(fee: HarbourFee, *, port_billing: PortBilling) -> LevyConfirmation:
    return await port_billing.levy(fee.amount, idempotency_key=str(fee.fee_id))
```

## Serialization

What a payload may publish - every field named, never a serialized domain object - is in
`SKILL.md`.

### A serialized type round-trips, and a test says so

**Why:** `from_wire(to_wire(value)) == value` is the contract a consumer relies on; a field that
serializes as a string and parses back as something else - a `Decimal` through a float, an aware
datetime through a naive one - corrupts data without an error. Every serialized type gets the test.

**Example:**
```python
# WRONG - the height goes out as a float and comes back with a different value
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class TideLevel:
    gauge_id: TideGaugeId
    height_metres: Decimal

    def to_wire(self) -> dict[str, object]:
        return {"gauge_id": str(self.gauge_id), "height_metres": float(self.height_metres)}

# CORRECT - the exact form goes out, and a round-trip test holds it there
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class TideLevel:
    gauge_id: TideGaugeId
    height_metres: Decimal

    def to_wire(self) -> dict[str, object]:
        return {"gauge_id": str(self.gauge_id), "height_metres": str(self.height_metres)}

    @classmethod
    def from_wire(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            gauge_id=TideGaugeId(UUID(str(payload["gauge_id"]))),
            height_metres=Decimal(str(payload["height_metres"])),
        )

def test_tide_level_round_trips_through_wire() -> None:
    level = TideLevel(gauge_id=TideGaugeId(UUID(int=7)), height_metres=Decimal("3.40"))

    restored = TideLevel.from_wire(level.to_wire())

    assert restored == level
```

### `NaN` and `Infinity` are refused where a payload arrives

**Why:** they are not JSON, yet `json.loads` turns them into floats, and a validator's `float` may
accept them even in strict mode until it is told to refuse them. One bad number then poisons every
sum it joins.

**Example:**
```python
# WRONG - json.loads returns nan and inf for constants no JSON document may contain
def parse_gauge_report(body: bytes) -> object:
    return json.loads(body)

# CORRECT - a non-standard constant is a malformed payload, refused where it arrives
def _reject_constant(name: str) -> Never:
    raise MalformedGaugeReportError(f"{name} is not a JSON number")

def parse_gauge_report(body: bytes) -> object:
    return json.loads(body, parse_constant=_reject_constant)
```

### A shape that is queued or stored carries its version

**Why:** once the shape changes, a consumer cannot tell an old message from a new one. Consumers of
stored and queued data tolerate unknown *added* fields and migrate an old version on read; a
request still rejects extras. Binary formats follow the same rules - explicit schema, explicit
version, adapters at the edge.
**Except:** a cache entry carries its version in its key, and an old entry is fetched again from the
source, never migrated.

## Files

A file is a boundary too: another process reads it, possibly while it is being written, possibly on
a machine with another locale.

### A file someone else reads is replaced, never rewritten in place

**Why:** a crash or a full disk mid-write leaves a truncated file where a whole one stood. A
temporary file in the same directory, flushed to disk and moved over the target with `os.replace`,
shows a reader the old file or the new one, never half of either; the same directory matters,
because a rename is atomic only within one filesystem. `delete_on_close=False` (3.12) keeps the file
through `close()` and still removes it when anything fails before the rename.

**Example:**
```python
# WRONG - a departure board can open the timetable half written
def publish_timetable(path: Path, timetable: bytes) -> None:
    path.write_bytes(timetable)

# CORRECT - written beside the target, flushed to disk, then renamed over it in one step
def publish_timetable(path: Path, timetable: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", delete_on_close=False
    ) as temporary:
        temporary.write(timetable)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary.close()
        os.replace(temporary.name, path)
```

## Time

### A datetime is aware UTC: refused without an offset at the boundary, stored as ISO-8601, local only for display

**Why:** a naive `datetime.now()` shifts with the server's zone and cannot be ordered against an
aware value; `utcnow()` is naive too. `"2026-03-01T09:00:00"` is an instant in no zone, and one
driver writes it into `timestamptz` in the client's local time. Epoch numbers are for metrics;
local time comes from `zoneinfo.ZoneInfo`, never a hand-written offset. `datetime.now(UTC)` appears only in the system clock; everything else asks an
injected `Clock` (`testing.md`).

**Example:**
```python
# WRONG - accepts an instant in no zone
def parse_berthed_at(raw: str) -> datetime:
    return datetime.fromisoformat(raw)

# CORRECT - a value without an offset is refused where it enters
def parse_berthed_at(raw: str) -> datetime:
    berthed_at = datetime.fromisoformat(raw)
    if berthed_at.tzinfo is None:
        raise MissingUtcOffsetError(raw)
    return berthed_at.astimezone(UTC)
```

### Elapsed time is added in UTC; a calendar day is a `date`

**Why:** wall-clock arithmetic on local times is wrong on the nights the clocks change - a crossing
of six hours lands at five or seven. Naive and aware values are never compared or mixed. A
timetable's service day is a `date`; stored as a midnight `datetime`, it invents a timezone bug.

**Example:**
```python
# WRONG - the crossing time is added on the destination's wall clock
def estimated_arrival(
    departed_at: datetime,
    *,
    destination_zone: ZoneInfo,
    crossing_duration: timedelta = _CROSSING_DURATION,
) -> datetime:
    return departed_at.astimezone(destination_zone) + crossing_duration

# CORRECT - elapsed time in UTC; the destination's zone is for display
def estimated_arrival(
    departed_at: datetime, *, crossing_duration: timedelta = _CROSSING_DURATION
) -> datetime:
    return departed_at.astimezone(UTC) + crossing_duration
```

### A deadline or an elapsed time is measured on the monotonic clock

**Why:** NTP steps the wall clock and an operator sets it: a step back stretches the wait, a step
forward ends it early. `time.monotonic()` - `loop.time()` in async code - only moves forward;
`datetime` is for the instants a person or a record reads. A duration is a `timedelta`, and one
stored as a number is an integer of an explicit unit, never a float of ambiguous unit.

**Example:**
```python
# WRONG - the wall clock: a clock step moves the deadline under the running loop
def wait_until_berth_clear(
    berth_id: BerthId,
    *,
    berths: BerthBoard,
    budget: timedelta = _CLEARANCE_BUDGET,
    poll_seconds: float = _CLEARANCE_POLL_SECONDS,
) -> bool:
    deadline = datetime.now(UTC) + budget
    while datetime.now(UTC) < deadline:
        if berths.status(berth_id) is BerthStatus.CLEAR:
            return True
        time.sleep(poll_seconds)
    return False

# CORRECT - the monotonic clock only moves forward
def wait_until_berth_clear(
    berth_id: BerthId,
    *,
    berths: BerthBoard,
    budget_seconds: float = _CLEARANCE_BUDGET_SECONDS,
    poll_seconds: float = _CLEARANCE_POLL_SECONDS,
) -> bool:
    deadline_seconds = time.monotonic() + budget_seconds
    while time.monotonic() < deadline_seconds:
        if berths.status(berth_id) is BerthStatus.CLEAR:
            return True
        time.sleep(poll_seconds)
    return False
```

## Money

### Money is a `Decimal` built from text, inside a value object with its currency, and a string on the wire

**Why:** a `float` cannot hold `19.99`, and a `Decimal` built from one inherits the error -
`19.989999999999998436805981327779591083526611328125`; the reader's JSON parser does the same to a
number, so `19.90` arrives as `19.9`, and the string carries the exact digits the consumer builds
its `Decimal` from. Amounts are quantized explicitly at the boundary -
`amount.quantize(Decimal("0.01"), ROUND_HALF_EVEN)` - and wrapped with their currency, so euros and
kroner cannot be added.

**Example:**
```python
# WRONG - built from a float, and carrying no currency
_HARBOUR_DUES: Final = 1.50

def crossing_fare(base_fare: float, *, harbour_dues: float = _HARBOUR_DUES) -> Decimal:
    return Decimal(base_fare + harbour_dues)

# CORRECT - built from the text the amount was written as, with its currency
_HARBOUR_DUES: Final = Fare(amount=Decimal("1.50"), currency=FareCurrency.EUR)

def crossing_fare(base_fare: Fare, *, harbour_dues: Fare = _HARBOUR_DUES) -> Fare:
    return base_fare + harbour_dues
```

## Identifiers

### A public identifier is random and opaque

**Why:** a sequential public id invites enumeration - whoever holds sailing 1042 asks for 1041 -
and a `random`-derived one is predictable. `uuid.uuid4()` for opaque ids; `uuid.uuid7()` (stdlib
from 3.14) when ids must sort by creation time for index locality; either is wrapped in its own
`NewType` (`naming.md`). An opaque id makes guessing harder; it never replaces the check that the
caller owns the resource.

