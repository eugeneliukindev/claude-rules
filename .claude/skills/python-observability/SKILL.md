---
name: python-observability
description: >-
  Chooses and wires metrics and traces beyond the logging rules: bounded attributes, histograms in
  seconds, OpenTelemetry names at module level with the SDK in the entry point, a correlation id in
  a contextvar, JSON log output. Use when code adds a metric, counter, histogram, span or request
  id, imports opentelemetry or prometheus_client, or configures logging.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Observability

How to write a log line, and that timing and counting are metrics, are `logging.md`; a trace is what
follows one request across processes. Below: which metric, where the tracer and the meter live, and
how log output is configured.

## Metrics

### A metric's attributes have bounded cardinality

**Why:** every distinct combination of attribute values is a separate time series, held in memory
and billed: a status class, a route template, a service tier — never a customer id, a bag id, a raw
URL path or an error message. A request metric labelled by raw path turned every id in a URL into a
new series until the route template became the default label. Span attributes follow the same rule,
and carry no personal data.

**Example:**
```python
# WRONG — the message carries ids, so every failure starts a time series of its own
def count_pickup_failure(error: Exception) -> None:
    _PICKUP_FAILURES.add(1, {"error": str(error)})


# CORRECT — the exception's type: a short list, known in advance
def count_pickup_failure(error: Exception) -> None:
    _PICKUP_FAILURES.add(1, {"error.type": type(error).__name__})
```

### A duration is a histogram in seconds, and an outcome is an attribute of one counter

**Why:** an average computed in the code hides the slow tail an alert needs; percentiles come from a
histogram. `succeeded` and `failed` as two counters make the failure rate a join across series that
drift apart; one counter with an `outcome` attribute makes it a ratio of one metric.

**Example:**
```python
# WRONG — two metrics: the failure rate is a join across series that drift apart
_WASH_CYCLES_SUCCEEDED: Final = _METER.create_counter("wash_cycles.succeeded")
_WASH_CYCLES_FAILED: Final = _METER.create_counter("wash_cycles.failed")


# CORRECT — one counter, and the outcome is an attribute of each event
_WASH_CYCLES_FINISHED: Final = _METER.create_counter("wash_cycles.finished")


def count_wash_cycle(outcome: CycleOutcome) -> None:
    _WASH_CYCLES_FINISHED.add(1, {"outcome": outcome.value})
```

## Tracer and Meter

### The tracer, the meter and its instruments are created once, at module level

**Why:** they are names the module records under, harmless until the entry point configures where
the records go (`modules.md`), and no dependency to inject. Created per call, an instrument is a
lookup at best and a new series at worst.

**Example:**
```python
# WRONG — the meter and the instrument are looked up again on every call
def record_pickup_duration(pickup: Pickup, *, elapsed_seconds: float) -> None:
    meter = metrics.get_meter(__name__)
    meter.create_histogram("pickup.duration", unit="s").record(elapsed_seconds)


# CORRECT — built once, recorded into on every call
_METER: Final = metrics.get_meter(__name__)
_PICKUP_DURATION: Final = _METER.create_histogram("pickup.duration", unit="s")


def record_pickup_duration(pickup: Pickup, *, elapsed_seconds: float) -> None:
    _PICKUP_DURATION.record(elapsed_seconds, {"service": pickup.service.value})
```

### Library and service code depend on `opentelemetry-api`; the SDK is configured in the entry point

**Why:** without configuration the API is a no-op, which is what a library's caller must be able to
choose; a module that installs a provider refuses the application's own, and a second
`set_tracer_provider` is ignored with a warning. The SDK, its exporters and sampling are set up once
in `main()`, like logging — never in a library or a test helper. Frameworks and clients are
instrumented with their instrumentation packages before spans are written by hand; a manual span
earns its place around a unit no library sees.

### Recording a signal never fails the work it observes

**Why:** a log line, a metric or a span whose value cannot be computed — a header that is not a
number, an exporter that is down — is caught and dropped inside the instrumentation, the way
`logging.Handler.handleError` does. A logging middleware that let a malformed request body escape
turned it into a 500 for a request that was otherwise served.

**Example:**
```python
# WRONG — a bag count the driver app sent as text makes the span fail the pickup it describes
def annotate_pickup_span(span: trace.Span, *, bag_count_header: str) -> None:
    span.set_attribute("pickup.bag_count", int(bag_count_header))


# CORRECT — an unreadable count is recorded as such, and the pickup goes on
def annotate_pickup_span(span: trace.Span, *, bag_count_header: str) -> None:
    try:
        bag_count = int(bag_count_header)
    except ValueError:
        span.set_attribute("pickup.bag_count_unreadable", True)
        return
    span.set_attribute("pickup.bag_count", bag_count)
```

## Correlation Ids

**Before tying the log lines of one request together, or propagating an id to another service, read
[correlation.md](correlation.md)** — a context variable set by the entry point, one filter that
stamps it, the trace id as the id.

- The id lives in a `ContextVar` set by the entry point, and one logging filter stamps it
- With OpenTelemetry, the trace id is the correlation id

## Log Output

**Before configuring logging — `basicConfig`, a handler, a formatter — read
[log-output.md](log-output.md)** — once, in the entry point, JSON lines with every `extra=` field,
the filter attached to the handler.

- Logging is configured once, in the entry point, by a formatter that writes every field as JSON
