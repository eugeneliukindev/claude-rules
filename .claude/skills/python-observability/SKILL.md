---
name: python-observability
description: >-
  Chooses and wires signals: logs, metrics and traces, bounded attributes, a correlation id in a
  contextvar, OpenTelemetry names at module level with the SDK in the entry point, JSON logs. Use
  when code adds a metric, counter, histogram, span or request id, imports opentelemetry or
  prometheus_client, or configures logging.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Observability

How to write a log line — levels, messages, `extra=`, no secrets — is `logging.md`; this file is the
rest: what is a log at all, and what is a metric or a trace instead. gRPC's metrics come from
`grpcio-observability`, not the OpenTelemetry instrumentation (`python-grpc`).

## One Question, One Signal

### An event gets the one signal its question needs

**Why:** a log is an event someone will read — an error, a decision, a state change — the most
expensive signal per event and the only one carrying a sentence. A metric is counted or measured,
aggregated before it leaves the process, so it is recorded on every request and alerted on; a
duration in a log line is a metric someone recovers with a regular expression. A trace follows one
request across processes. "How many transcodes failed per minute" is a counter; "why did video 42
fail" is a log line, once, at the boundary that handled it.

## Metrics

### A metric's attributes have bounded cardinality

**Why:** every distinct combination of attribute values is a separate time series, held in memory
and billed: a status class, a route template, a codec — never a user id, a video id, a raw URL path
or an error message. A request metric labelled by raw path turned every id in a URL into a new
series until the route template became the default label. Span attributes follow the same rule, and
carry no personal data.

**Example:**
```python
# WRONG — the message carries ids, so every failure starts a time series of its own
def count_upload_failure(error: Exception) -> None:
    _UPLOAD_FAILURES.add(1, {"error": str(error)})


# CORRECT — the exception's type: a short list, known in advance
def count_upload_failure(error: Exception) -> None:
    _UPLOAD_FAILURES.add(1, {"error.type": type(error).__name__})
```

### A duration is a histogram in seconds, and an outcome is an attribute of one counter

**Why:** an average computed in the code hides the slow tail an alert needs; percentiles come from a
histogram. `succeeded` and `failed` as two counters make the failure rate a join across series that
drift apart; one counter with an `outcome` attribute makes it a ratio of one metric.

**Example:**
```python
# WRONG — two metrics: the failure rate is a join across series that drift apart
_TRANSCODES_SUCCEEDED: Final = _METER.create_counter("transcodes.succeeded")
_TRANSCODES_FAILED: Final = _METER.create_counter("transcodes.failed")


# CORRECT — one counter, and the outcome is an attribute of each event
_TRANSCODES_FINISHED: Final = _METER.create_counter("transcodes.finished")


def count_transcode(outcome: Outcome) -> None:
    _TRANSCODES_FINISHED.add(1, {"outcome": outcome.value})
```

## Module-Level Names

### The tracer, the meter and its instruments are module-level names, like the logger

**Why:** `python-wiring` allows constants and the logger at module level, and these are the same
kind of thing: a name the module records under, harmless until the entry point configures where
the records go, and no dependency to inject. Created per call, an instrument is a lookup at best and
a new series at worst.

**Example:**
```python
# WRONG — the meter and the instrument are looked up again on every call
def close_transcode(job: TranscodeJob, *, elapsed_seconds: float) -> None:
    meter = metrics.get_meter(__name__)
    meter.create_histogram("transcode.duration", unit="s").record(elapsed_seconds)


# CORRECT — built once, recorded into on every call
_METER: Final = metrics.get_meter(__name__)
_TRANSCODE_DURATION: Final = _METER.create_histogram("transcode.duration", unit="s")


def close_transcode(job: TranscodeJob, *, elapsed_seconds: float) -> None:
    _TRANSCODE_DURATION.record(elapsed_seconds, {"codec": job.codec.value})
```

### Library and service code depend on `opentelemetry-api`; the SDK is configured in the entry point

**Why:** without configuration the API is a no-op, which is what a library's caller must be able to
choose; a module that installs a provider on import refuses the application's own. The SDK, its
exporters and sampling are set up once in `main()`, like logging — never in a library, on import,
or in a test helper. Frameworks and clients are instrumented with their instrumentation packages
before spans are written by hand; a manual span earns its place around a unit no library sees.

### Recording a signal never fails the work it observes

**Why:** a log line, a metric or a span that raises — a body that will not serialise, an exporter
that is down — is caught and dropped inside the instrumentation, the way
`logging.Handler.handleError` does. A logging middleware that let a malformed request body escape
turned it into a 500 for a request that was otherwise served.

**Example:**
```python
# WRONG — a body that is not JSON makes the logging fail the request it was only describing
def log_request_body(body: bytes) -> None:
    logger.debug("request body", extra={"body": json.loads(body)})


# CORRECT — an unreadable body is described as such, and the request goes on
def log_request_body(body: bytes) -> None:
    try:
        parsed: object = json.loads(body)
    except ValueError:
        parsed = f"<{len(body)} bytes, not JSON>"
    logger.debug("request body", extra={"body": parsed})
```

## Correlation Ids

**Before tying the log lines of one request together, or propagating an id to another service, read
[correlation.md](correlation.md)** — a context variable set by the entry point, one filter that
stamps it, the trace id as the id.

## Log Output

**Before configuring logging in an entry point, read [log-output.md](log-output.md)** — JSON lines
with every `extra=` field, the filter attached to the handler.
