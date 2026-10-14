# Correlation Ids

Every log line of one request carries the same id, or the lines of fifty concurrent requests
interleave into a log nobody can follow.

### The id lives in a `ContextVar` set by the entry point, and one logging filter stamps it

**Why:** a context variable follows the request across `await`s and into `asyncio.to_thread`, where
a global or a thread-local would not. The entry point — a middleware, a message consumer — sets it
and resets it with the token in `finally`; one filter attached to the handler writes it onto every
record, so no call site passes the id by hand, and none can forget it.

**Example:**
```python
# WRONG — the id threaded by hand through every signature, until one call site forgets it
def confirm_pickup(pickup: Pickup, request_id: str) -> None:
    logger.info("pickup confirmed", extra={"request_id": request_id, "pickup_id": pickup.pickup_id})


# CORRECT — the filter stamps the id; the call site names only its own fields
request_id: Final = ContextVar[str]("request_id", default=_UNKNOWN_REQUEST_ID)


@final
class RequestIdFilter(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def confirm_pickup(pickup: Pickup) -> None:
    logger.info("pickup confirmed", extra={"pickup_id": pickup.pickup_id})
```

### With OpenTelemetry, the trace id is the correlation id

**Why:** a request id minted beside the trace leaves logs and spans that cannot be joined; the
propagator already sends the trace id on outbound calls, so the next service logs the same one. The
filter reads it from the current span, as the 32 hex digits `trace.format_trace_id` writes and
tracing backends show.

**Example:**
```python
# WRONG — a request id of its own beside the trace: logs and spans cannot be joined
@final
class CorrelationFilter(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


# CORRECT — the current span's trace id
@final
class CorrelationFilter(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        span_context = trace.get_current_span().get_span_context()
        record.trace_id = (
            trace.format_trace_id(span_context.trace_id)
            if span_context.is_valid
            else _UNKNOWN_TRACE_ID
        )
        return True
```
