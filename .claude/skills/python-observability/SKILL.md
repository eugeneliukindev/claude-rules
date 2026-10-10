---
name: python-observability
description: >-
  Python observability: which signal answers which question — a log someone reads, a metric that
  is counted, a trace that follows one request; counters and histograms with bounded attributes
  instead of a log line per event; a correlation id carried by a contextvar and stamped on every
  log record by one filter; OpenTelemetry tracer and meter as module-level names like the logger,
  with the SDK configured only in the entry point; logs written as JSON. Use when Python code adds
  a metric, a counter, a histogram, a span, a request id or correlation id, imports opentelemetry or
  prometheus_client, or configures logging.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Observability

How to write a log line — levels, messages, `extra=`, no secrets — is in `logging.md`. This file is
the rest: what is a log at all, and what is a metric or a trace instead.

## One Question, One Signal

- **A log is an event someone will read**: an error, a decision, a state change worth explaining
  afterwards. It is the most expensive signal per event and the only one that carries a sentence.
- **A metric is something counted or measured**: requests, failures, durations, queue depth, batch
  sizes. It is cheap per event because it is aggregated before it leaves the process, so it can be
  recorded on every request and alerted on. A duration written into a log line is a metric someone
  has to recover with a regular expression.
- **A trace follows one request across processes**: where the time went and which call failed.
- **An event gets the signal its question needs, and one of them.** "How many orders failed per
  minute" is a counter; "why did order 42 fail" is a log line, once, at the boundary that handled
  it.

```python
# WRONG — a log line per checkout to be grepped for a number, keyed by an unbounded id
logger.info("checkout finished", extra={"order_id": order.order_id, "seconds": elapsed_seconds})

# CORRECT — a histogram, with an attribute whose values can be listed
_CHECKOUT_DURATION.record(elapsed_seconds, {"payment_method": order.payment_method.value})
```

## Metrics

- **Attributes have bounded cardinality.** Every distinct combination of attribute values is a
  separate time series, held in memory and billed: a status class, a route *template*, a payment
  method — never a user id, an order id, a raw URL path or an error message. A request metric
  labelled by raw path turned every id in a URL into a new series until the route template became
  the default label.

```python
# WRONG — the message carries ids, so every failure starts a time series of its own
_PAYMENT_FAILURES.add(1, {"error": str(error)})

# CORRECT — the exception's type: a short list, known in advance
_PAYMENT_FAILURES.add(1, {"error.type": type(error).__name__})
```

- **Durations are histograms in seconds**, never an average computed in the code; the percentiles
  are what an alert needs, and an average hides the slow tail.
- **Counters count outcomes**: `succeeded` and `failed` as one counter with an `outcome` attribute,
  so the failure rate is a ratio of one metric.

```python
# WRONG — two metrics: the failure rate is a join across series that drift apart
_ORDERS_SUCCEEDED: Final = _METER.create_counter("orders.succeeded")
_ORDERS_FAILED: Final = _METER.create_counter("orders.failed")

# CORRECT — one counter, and the outcome is an attribute of each event
_ORDERS_PROCESSED: Final = _METER.create_counter("orders.processed")

_ORDERS_PROCESSED.add(1, {"outcome": Outcome.FAILED.value})
```

- **Instruments are created once, at module level**, next to the logger (below). Creating one per
  call is a lookup at best and a new series at worst.

## Module-Level Names

`python-wiring` allows constants and the logger at module level. **The tracer, the meter and its
instruments, and a context variable are the same kind of thing**, and the same carve-out holds:
each is a name the module records under, harmless until the entry point configures where the
records go, and none of them is a dependency to inject.

```python
# WRONG — the meter and the instrument are looked up again on every call
def close_checkout(checkout: Checkout, elapsed_seconds: float) -> None:
    ...
    meter = metrics.get_meter(__name__)
    meter.create_histogram("checkout.duration", unit="s").record(elapsed_seconds)

# CORRECT — module-level names like the logger: built once, recorded into on every call
_TRACER: Final = trace.get_tracer(__name__)
_METER: Final = metrics.get_meter(__name__)
_CHECKOUT_DURATION: Final = _METER.create_histogram("checkout.duration", unit="s")

def close_checkout(checkout: Checkout, elapsed_seconds: float) -> None:
    ...
    _CHECKOUT_DURATION.record(elapsed_seconds)
```

- **Library and service code depends on `opentelemetry-api` only.** The SDK, its exporters and
  sampling are configured in the entry point, like logging; without that configuration the API is
  a no-op, which is what a library's caller must be able to choose.

```python
# WRONG — orders/checkout.py installs a provider on import; the application's own is then refused
trace.set_tracer_provider(TracerProvider())
_TRACER: Final = trace.get_tracer(__name__)

# CORRECT — orders/checkout.py asks the API for a tracer; main() alone installs the SDK
_TRACER: Final = trace.get_tracer(__name__)

def main() -> None:
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    ...
```

- **Instrument frameworks and clients with their instrumentation packages** before writing spans by
  hand; a manual span earns its place around a unit of work no library sees — a batch, a use case.
  The OpenTelemetry gRPC instrumentation records traces only; gRPC's metrics come from
  `grpcio-observability` (`python-grpc`).
- **Span attributes follow the metric rule** — bounded, and no PII.

## Correlation Ids

Every log line of one request carries the same id, or the lines of fifty concurrent requests
interleave into a log nobody can follow.

- **The id lives in a `ContextVar`**, set by the entry point — the middleware, the message
  consumer — and reset when the request ends. A context variable follows the request across
  `await`s and `asyncio.to_thread`, where a global or a thread-local would not (`python-async`).
- **One logging filter stamps it on every record**, attached to the handler in the entry point. No
  call site passes the id by hand, and none can forget it.

```python
_UNKNOWN_REQUEST_ID: Final = "-"

request_id: Final = ContextVar[str]("request_id", default=_UNKNOWN_REQUEST_ID)


@final
class RequestIdFilter(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True
```

The entry point sets it around each request — `token = request_id.set(incoming_id)`, then
`request_id.reset(token)` in `finally` — and the JSON formatter below writes it as a field of
every line, like any other attribute on the record.

```python
# WRONG — the id threaded by hand through every signature, until one call site forgets it
def capture_payment(order: Order, request_id: str) -> None:
    ...
    logger.info("payment captured", extra={"request_id": request_id, "order_id": order.order_id})

# CORRECT — the filter stamps the id; the call site names only its own fields
def capture_payment(order: Order) -> None:
    ...
    logger.info("payment captured", extra={"order_id": order.order_id})
```

- **The id travels on outbound calls** as a header, so the next service logs the same one. With
  OpenTelemetry, the trace id is that id and its propagator sends it; do not mint a second one.

- **Recording a signal never fails the work it observes.** A log line, a metric or a span that
  raises — a body that will not serialise, an exporter that is down — is caught and dropped inside
  the instrumentation, the way `logging.Handler.handleError` does. A logging middleware that let a
  malformed request body escape turned it into a 500 for a request that was otherwise served.

## Configuring Output

- **Logging is configured once, in the entry point, and writes JSON** (`logging.md`): handlers,
  levels, a JSON formatter, the filter above.

```python
# WRONG — a format string prints only the fields it names: every extra= field is dropped
def _configure_logging(level: int) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# CORRECT — one JSON object per line, with every extra= field the call sites and the filter add
_BUILTIN_FIELDS: Final = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

@final
class JsonFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry |= {key: value for key, value in vars(record).items() if key not in _BUILTIN_FIELDS}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)

def _configure_logging(level: int) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    logging.basicConfig(level=level, handlers=[handler])
```

- **Never configure logging or telemetry on import**, in a library, or in a test helper — the
  application that imports it has already chosen.
