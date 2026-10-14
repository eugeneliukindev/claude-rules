# Log Output

### Logging is configured once, in the entry point, by a formatter that writes every field as JSON

**Why:** a library that configures the root logger reconfigures every application that imports it —
a framework that did took a major version to undo — so `main()` configures it, once. A format string
prints only the fields it names, so every `extra=` field and the filter's id are dropped; one JSON
object per line keeps them all as fields a search can filter on. `default=str` keeps a value `json`
cannot encode from failing the line.

**Example:**
```python
# WRONG — a format string prints only the fields it names: every extra= field is dropped
def configure_logging(level: int) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# CORRECT — one JSON object per line, with every extra= field the call sites and the filter add
_BUILTIN_FIELDS: Final = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


@final
class JsonLinesFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        line |= {key: value for key, value in vars(record).items() if key not in _BUILTIN_FIELDS}
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def configure_logging(level: int) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLinesFormatter())
    handler.addFilter(CorrelationFilter())
    logging.basicConfig(level=level, handlers=[handler])
```
