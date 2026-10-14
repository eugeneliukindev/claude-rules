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

**Why:** two families, two jobs. A validating model — a request or response, a message payload,
settings, a row from an untrusted source — parses external data, and it is the only place that
happens; domain code never imports the validation library. The edge validates once and passes a
domain object inward, so a check repeated in a service means the boundary leaked. Boundary models
are strict: no `"1"` coerced to `1`, no unknown field quietly dropped. A bare collection is
validated through one adapter instance built once — constructing the validator is the cost.

**Example:**
```python
# WRONG — the planner takes the request model and re-checks what the boundary should have
@final
class BerthPlanner:
    def __init__(self, *, allocations: BerthAllocations) -> None:
        self._allocations = allocations

    def allocate(self, request: BerthAllocationRequest) -> AllocationId:
        if request.departs_at <= request.arrives_at:
            raise EmptyBerthWindowError(request.arrives_at, request.departs_at)
        return self._allocations.add(request.to_domain())


# CORRECT — the edge parsed and converted; BerthWindow refuses an empty window when it is built
@final
class BerthPlanner:
    def __init__(self, *, allocations: BerthAllocations) -> None:
        self._allocations = allocations

    def allocate(self, allocation: BerthAllocation) -> AllocationId:
        return self._allocations.add(allocation)
```

### The two families are mapped field by field, never by splatting one into the other

**Why:** the splat is typed `Any`, so a field renamed on either side passes the type check and
fails in production; named fields fail the check on the line that maps them.

**Example:**
```python
# WRONG — asdict() feeds BerthAllocation whatever keys the request happens to have
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class BerthAllocationRequest:
    berth_id: UUID
    arrives_at: datetime
    departs_at: datetime

    def to_domain(self) -> BerthAllocation:
        return BerthAllocation(**asdict(self))


# CORRECT — every field named once, so a rename on either side is a type error here
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class BerthAllocationRequest:
    berth_id: UUID
    arrives_at: datetime
    departs_at: datetime

    def to_domain(self) -> BerthAllocation:
        return BerthAllocation(
            berth_id=BerthId(self.berth_id),
            window=BerthWindow(arrives_at=self.arrives_at, departs_at=self.departs_at),
        )
```

### A field-by-field copy is a method on the schema; a mapping with rules is a function beside it

**Why:** once the view hides a field by permission, converts a currency or computes a total, a
schema that maps itself answers to two actors — the API's shape and the view's rules. The mapping
moves to a function in the same boundary module, and the schema stays a shape.

**Example:**
```python
# WRONG — the response model owns who may see the master's phone number
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


# CORRECT — the shape stays a shape; the view's rule is a function beside it
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

**Why:** what a serializer can reach, it will publish — a password hash today, every field added
tomorrow. Over-exposure is a security bug, not a formatting one, so the boundary builds its output
from the domain object field by field and never serializes a domain or ORM object, `__dict__` or
`vars()` by accident.

## External Calls

### Every call that leaves the process has an explicit timeout

**Why:** HTTP, a database, a queue, a cache, DNS — a call with no timeout turns a dependency's
outage into your own: a server that accepts the connection and never answers holds the worker
forever. Client defaults are set once where the client is built; a call overrides them only with a
named constant.

### Only a transient failure is retried, and the adapter classifies it once

**Why:** a connect or read timeout, a rate limit, a server error, a broker disconnect pass with
time; a business rejection, a validation error or an auth failure does not, and retrying a conflict
is a loop, not resilience. The adapter translates upstream errors (`errors.md`) into a transient and
a permanent type, and the retry policy keys on the type — bounded, exponential and jittered, with
the numbers named in the adapter. A pool that let the event loop's own timeout escape untranslated
broke every caller that caught the library's documented timeout error.
**Except:** a cache read is not retried even when the failure is transient — the source is its
fallback.

**Example:**
```python
# WRONG — one error type for every status, so the policy retries a 404 like a 503
def _raise_for_tide_status(status_code: int, harbour: HarbourCode) -> None:
    if status_code >= HTTPStatus.BAD_REQUEST:
        raise TideServiceError(f"tides for {harbour}: service answered {status_code}")


# CORRECT — classified once, here; the retry policy keys on TransientTideError alone
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

### A write is retried only with an idempotency key the operation minted before its first attempt

**Why:** a client that times out after the server committed, and retries with a fresh key, levies
the operator twice. Where the API takes no key, the operation is made idempotent on your side, or
it is not retried.

**Example:**
```python
# WRONG — every attempt mints a new key, so the port authority sees three different levies
@_RETRY_LEVY
async def _levy_harbour_fee(fee: HarbourFee, *, port_billing: PortBilling) -> LevyConfirmation:
    return await port_billing.levy(fee.amount, idempotency_key=str(uuid.uuid4()))


# CORRECT — the fee's own id, minted when the fee was assessed, is the key
@_RETRY_LEVY
async def _levy_harbour_fee(fee: HarbourFee, *, port_billing: PortBilling) -> LevyConfirmation:
    return await port_billing.levy(fee.amount, idempotency_key=str(fee.fee_id))
```

### Retries happen at one level, the adapter, and the outermost boundary owns the deadline

**Why:** budgets nest multiplicatively — four attempts inside a caller that also makes four is
sixteen, and a five-second budget becomes eighty. A service sees one call that succeeded or raised a
final error; a client's built-in retry policy, where it has one, is that level. When a dependency
keeps failing, the adapter stops calling it and raises an unavailability error, so callers degrade
deliberately instead of queueing timeouts.
**Except:** a deadlock or serialization failure is retried above the adapter, by rerunning the whole
transaction.

**Example:**
```python
# WRONG — the schedule retries an adapter that already retries: up to sixteen calls per request
@final
class SailingSchedule:
    def __init__(self, *, tides: TideClient, attempts: int = _TIDE_ATTEMPTS) -> None:
        self._tides = tides
        self._attempts = attempts

    def tide_table(self, harbour: HarbourCode) -> TideTable:
        for _ in range(self._attempts):
            with contextlib.suppress(TransientTideError):
                return self._tides.fetch_tide_table(harbour)
        raise TideTableUnavailableError(harbour)


# CORRECT — the adapter retried; what reaches the schedule is final
@final
class SailingSchedule:
    def __init__(self, *, tides: TideClient) -> None:
        self._tides = tides

    def tide_table(self, harbour: HarbourCode) -> TideTable:
        return self._tides.fetch_tide_table(harbour)
```

## Serialization

**Before writing code that turns a value into bytes or text for another process — JSON, a queued
message, a stored payload — or parses one back, read [serialization.md](serialization.md)** — the
round-trip test, `NaN` and `Infinity` refused, a version on every queued or stored shape.

- A serialized type round-trips, and a test says so
- `NaN` and `Infinity` are refused where a payload arrives
- A shape that is queued or stored carries its version

## Files

**Before writing a file another process reads, read [files.md](files.md)** — a temporary file in
the same directory, flushed to disk and moved over the target in one step.

- A file someone else reads is replaced, never rewritten in place

## Time

**Before writing code that creates, compares, stores or serializes a `datetime`, measures a deadline
or holds a duration, read [time.md](time.md)** — aware UTC, offsets required at the edge, arithmetic
in UTC, `date` for calendar days, the injected clock, monotonic deadlines.

- A datetime is timezone-aware UTC; local time exists only at the presentation edge
- A boundary rejects a datetime without an offset, and stores it as ISO-8601
- Elapsed time is added in UTC; a calendar day is a `date`
- A deadline or an elapsed time is measured on the monotonic clock

## Money

**Before writing code that holds, adds, rounds or sends an amount of money, read
[money.md](money.md)** — `Decimal` built from text inside a value object with its currency, and a
string on the wire.

- Money is a `Decimal` built from text, inside a value object with its currency
- On the wire an amount is a string

## Identifiers

**Before minting or exposing an identifier, read [identifiers.md](identifiers.md)** — random,
opaque public ids, `uuid4` or `uuid7`.

- A public identifier is random and opaque
