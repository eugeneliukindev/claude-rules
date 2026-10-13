# Log Output

### Logging is configured once, at the entry point, and writes JSON

**Why:** a library or an import that configures the root logger reconfigures every application that
imports it — a framework that did took a major version to undo; JSON, one object per line, turns
every `extra=` field into a field a search can filter on.

**Example:**
```python
# WRONG — configured on import, in a module others import
logging.basicConfig(level=logging.INFO)


def capture(payment: Payment) -> None:
    logger.info("payment captured", extra={"payment_id": payment.payment_id})


# CORRECT — the entry point configures it, once
def main() -> None:
    configure_json_logging(level=logging.INFO)
    run_worker()
```


### A log line is one JSON object, from a formatter that keeps every `extra=` field

**Why:** a format string prints only the fields it names, so every `extra=` field and the filter's
id are dropped. A JSON formatter writes every attribute the call sites and the filters add; it is
attached with the filter in the entry point, as above.

**Example:**
```python
# WRONG — a format string prints only the fields it names: every extra= field is dropped
def configure_logging(level: int) -> None:
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


def configure_logging(level: int) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationFilter())
    logging.basicConfig(level=level, handlers=[handler])
```
