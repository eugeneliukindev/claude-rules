---
name: python-boundaries
description: >-
  Designs what crosses a process boundary: validation at the edge, timeouts, retries and
  idempotency, serialization, files other processes read, time, money and identifiers. Use when
  code calls HTTP, a queue, a cache, a database or a file, writes a payload for another process,
  or handles datetimes, Decimal amounts or UUIDs. Not for niquests or httpx calls (python-
  niquests).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Boundaries

The library mechanics behind these rules: a validating model in pydantic is `python-pydantic`, a
retry policy's numbers are `python-tenacity`, a gRPC channel's retries `python-grpc`.

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
# WRONG — the service takes the request model and re-checks what the boundary should have
@final
class BookingService:
    def __init__(self, *, bookings: BookingRepository) -> None:
        self._bookings = bookings

    def book(self, request: BookingRequest) -> BookingId:
        if request.check_out <= request.check_in:
            raise EmptyStayError(request.check_in, request.check_out)
        return self._bookings.add(request.to_domain())


# CORRECT — the edge parsed and converted; Stay refuses an empty stay when it is built
@final
class BookingService:
    def __init__(self, *, bookings: BookingRepository) -> None:
        self._bookings = bookings

    def book(self, booking: Booking) -> BookingId:
        return self._bookings.add(booking)
```

### The two families are mapped field by field, never by splatting one into the other

**Why:** the splat is typed `Any`, so a field renamed on either side passes the type check and
fails in production; named fields fail the check on the line that maps them.

**Example:**
```python
# WRONG — asdict() feeds Booking whatever keys the request happens to have
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class BookingRequest:
    room_id: UUID
    check_in: date
    check_out: date

    def to_domain(self) -> Booking:
        return Booking(**asdict(self))


# CORRECT — every field named once, so a rename on either side is a type error here
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class BookingRequest:
    room_id: UUID
    check_in: date
    check_out: date

    def to_domain(self) -> Booking:
        return Booking(
            room_id=RoomId(self.room_id),
            stay=Stay(check_in=self.check_in, check_out=self.check_out),
        )
```

### A field-by-field copy is a method on the schema; a mapping with rules is a function beside it

**Why:** once the view hides a field by permission, converts a currency or computes a total, a
schema that maps itself answers to two actors — the API's shape and the view's rules. The mapping
moves to a function in the same boundary module, and the schema stays a shape.

**Example:**
```python
# WRONG — the response model owns who may see the author's email
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ArticleResponse:
    title: str
    body: str
    author_email: str | None

    @classmethod
    def from_domain(cls, article: Article, *, viewer: Principal) -> Self:
        is_visible = viewer.user_id == article.author_id or viewer.is_editor
        return cls(
            title=article.title,
            body=article.body,
            author_email=article.author_email if is_visible else None,
        )


# CORRECT — the shape stays a shape; the view's rule is a function beside it
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ArticleResponse:
    title: str
    body: str
    author_email: str | None


def article_response(article: Article, *, viewer: Principal) -> ArticleResponse:
    is_visible = viewer.user_id == article.author_id or viewer.is_editor
    return ArticleResponse(
        title=article.title,
        body=article.body,
        author_email=article.author_email if is_visible else None,
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
is a loop, not resilience. The adapter translates upstream errors into a transient and a permanent
type, and the retry policy keys on the type — bounded, exponential and jittered, with the numbers
named in the adapter. A pool that let the event loop's own timeout escape untranslated broke every
caller that caught the library's documented timeout error. A cache read is not retried even when the
failure is transient: the source is its fallback (`python-caching`).

**Example:**
```python
# WRONG — one error type for every status, so the policy retries a 404 like a 503
def _raise_for_status(status_code: int, tracking_number: TrackingNumber) -> None:
    if status_code >= HTTPStatus.BAD_REQUEST:
        raise CarrierError(f"parcel {tracking_number}: carrier answered {status_code}")


# CORRECT — classified once, here; the retry policy keys on TransientCarrierError alone
_TRANSIENT_STATUSES: Final = frozenset(
    {
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)


def _raise_for_status(status_code: int, tracking_number: TrackingNumber) -> None:
    if status_code in _TRANSIENT_STATUSES:
        raise TransientCarrierError(f"parcel {tracking_number}: carrier answered {status_code}")
    if status_code >= HTTPStatus.BAD_REQUEST:
        raise PermanentCarrierError(f"parcel {tracking_number}: carrier answered {status_code}")
```

### A write is retried only with an idempotency key the operation minted before its first attempt

**Why:** a client that times out after the server committed, and retries with a fresh key, charges
the customer twice. Where the API takes no key, the operation is made idempotent on your side, or
it is not retried.

**Example:**
```python
# WRONG — every attempt mints a new key, so the gateway sees three different charges
@_RETRY_TRANSIENT
async def _charge(payment: Payment, *, gateway: PaymentGateway) -> Receipt:
    return await gateway.charge(payment.amount, idempotency_key=str(uuid.uuid4()))


# CORRECT — the payment's own id, minted when the payment was created, is the key
@_RETRY_TRANSIENT
async def _charge(payment: Payment, *, gateway: PaymentGateway) -> Receipt:
    return await gateway.charge(payment.amount, idempotency_key=str(payment.payment_id))
```

### A consumer tolerates the same message twice, keyed on the event's own id

**Why:** at-least-once delivery redelivers after a crash between the effect and the
acknowledgement. The id that makes a repeat harmless travels in the payload — the broker's id
changes on redelivery; how a consumer records it is in `python-workers`.

**Example:**
```python
# WRONG — a redelivered purchase awards the points a second time
def award_points(message: PurchaseCompleted, *, ledger: LoyaltyLedger) -> None:
    ledger.award(message.member_id, message.points)


# CORRECT — the ledger stores the event id with the award in one write, and refuses a repeat
def award_points(message: PurchaseCompleted, *, ledger: LoyaltyLedger) -> None:
    ledger.award_once(message.event_id, member_id=message.member_id, points=message.points)
```

### An operation promises a state, so a repeat of it succeeds

**Why:** a retry, a redelivery or a double click cancels what the first call already cancelled; an
error there turns a success into a failure every caller must special-case — "define errors out of
existence". A state the call cannot reach is still an error, and a guess is never one in its place:
a clipped index or an empty result for "not found" is a wrong answer that looks right.

**Example:**
```python
# WRONG — a retried cancel fails on the subscription the first attempt already cancelled
def cancel_subscription(subscription_id: SubscriptionId, *, subscriptions: Subscriptions) -> None:
    subscription = subscriptions.get(subscription_id)
    if subscription.status is SubscriptionStatus.CANCELLED:
        raise SubscriptionAlreadyCancelledError(subscription_id)
    if subscription.status is SubscriptionStatus.EXPIRED:
        raise SubscriptionExpiredError(subscription_id)
    subscriptions.save(replace(subscription, status=SubscriptionStatus.CANCELLED))


# CORRECT — "cancelled afterwards" holds after a repeat too; only the unreachable state raises
def cancel_subscription(subscription_id: SubscriptionId, *, subscriptions: Subscriptions) -> None:
    subscription = subscriptions.get(subscription_id)
    if subscription.status is SubscriptionStatus.CANCELLED:
        return
    if subscription.status is SubscriptionStatus.EXPIRED:
        raise SubscriptionExpiredError(subscription_id)
    subscriptions.save(replace(subscription, status=SubscriptionStatus.CANCELLED))
```

### Retries happen at one level, the adapter, and the outermost boundary owns the deadline

**Why:** budgets nest multiplicatively — four attempts inside a caller that also makes four is
sixteen, and a five-second budget becomes eighty. A service sees one call that succeeded or raised a
final error; a client's built-in retry policy, where it has one, is that level. The one retry above
the adapter is a deadlock or serialization failure, which retries the whole transaction
(`python-persistence`). When a dependency keeps failing, the adapter stops calling it and raises an
unavailability error, so callers degrade deliberately instead of queueing timeouts.

**Example:**
```python
# WRONG — the service retries an adapter that already retries: up to sixteen calls per request
@final
class WeatherReport:
    def __init__(self, *, forecasts: ForecastClient, attempts: int = _ATTEMPTS) -> None:
        self._forecasts = forecasts
        self._attempts = attempts

    def today(self, city: City) -> Forecast:
        for _ in range(self._attempts):
            with contextlib.suppress(TransientUpstreamError):
                return self._forecasts.fetch(city)
        raise ForecastUnavailableError(city)


# CORRECT — the adapter retried; what reaches the service is final
@final
class WeatherReport:
    def __init__(self, *, forecasts: ForecastClient) -> None:
        self._forecasts = forecasts

    def today(self, city: City) -> Forecast:
        return self._forecasts.fetch(city)
```

## Serialization

**Before writing code that turns a value into bytes or text for another process — JSON, a queued
message, a stored payload — or parses one back, read [serialization.md](serialization.md)** — the
round-trip test, `NaN` and `Infinity` refused, a version on every queued or stored shape.

## Files

**Before writing a file another process reads, read [files.md](files.md)** — a temporary file in
the same directory, flushed to disk and moved over the target in one step.

## Time

**Before writing code that creates, compares, stores or serializes a `datetime`, measures a deadline
or holds a duration, read [time.md](time.md)** — aware UTC, offsets required at the edge, arithmetic
in UTC, `date` for calendar days, the injected clock, monotonic deadlines.

## Money

**Before writing code that holds, adds, rounds or sends an amount of money, read
[money.md](money.md)** — `Decimal` built from text inside a value object with its currency, and a
string on the wire.

## Identifiers

**Before minting or exposing an identifier, read [identifiers.md](identifiers.md)** — random,
opaque public ids wrapped in a `NewType`, `uuid4` or `uuid7`.
