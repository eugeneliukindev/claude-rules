# Settings and Startup

The composition root and resource lifetime are in `SKILL.md`; the settings model in pydantic is
`python-pydantic`, and FastAPI's form of the settings accessor is `python-fastapi`.

## Contents

- Configuration is typed settings, built once at the root and unpacked there
- The server's settings are a class apart from the application's
- Behaviour never branches on the deployment environment's name
- Tests never build `Settings`; they pass fields
- Configuration is validated at startup, before serving
- A secret never appears in code, in a default or in a log

## The Settings Object

### Configuration is typed settings, built once at the root and unpacked there

**Why:** anything that varies by environment read from `os.environ` across the code is a dependency
nobody declared; a module-level settings instance — or a cached `get_settings()` behind `@lru_cache`
— is that instance by another name, global, and changed in a test only through `cache_clear()` and
the environment. Below the root nothing takes the settings object (`functions.md`).

**Example:**
```python
# WRONG — a global behind a function: every caller reaches it, and no test can hand in another
@lru_cache
def get_settings() -> Settings:
    return Settings()


def fetch_rates(*, client: HttpClient) -> RateTable:
    settings = get_settings()
    return client.get_rates(settings.rates_url, timeout_seconds=settings.rates_timeout_seconds)


# CORRECT — built once by the root, which unpacks the fields each part needs
def fetch_rates(*, client: HttpClient, rates_url: str, timeout_seconds: float) -> RateTable:
    return client.get_rates(rates_url, timeout_seconds=timeout_seconds)


def main() -> None:
    settings = Settings()
    with managed_http_client(settings.http_timeout_seconds) as client:
        rates = fetch_rates(
            client=client,
            rates_url=settings.rates_url,
            timeout_seconds=settings.rates_timeout_seconds,
        )
        publish_rates(rates)
```

### The server's settings are a class apart from the application's

**Why:** the host, the port and the drain configure the process that serves; the database URL and
the limits configure what it serves. One class holding both makes every entry point supply all of
it — a worker running the same use cases cannot start without a port it never binds — and lets the
application's fields grow server knobs. Each entry point builds the classes of the parts it runs.

**Example:**
```python
# WRONG — one class: the worker needs HOST and PORT set before it starts
def serve_main() -> None:
    settings = Settings()
    serve(build_app(database_url=settings.database_url), host=settings.host, port=settings.port)


def worker_main() -> None:
    settings = Settings()
    run_worker(database_url=settings.database_url)


# CORRECT — each entry point builds what it runs, and the worker knows nothing of the server
def serve_main() -> None:
    server_settings = ServerSettings()
    app_settings = AppSettings()
    serve(
        build_app(database_url=app_settings.database_url),
        host=server_settings.host,
        port=server_settings.port,
    )


def worker_main() -> None:
    app_settings = AppSettings()
    run_worker(database_url=app_settings.database_url)
```

### Behaviour never branches on the deployment environment's name; each difference is a setting

**Why:** `if environment == "production"` is code that runs for the first time in the environment it
guards, and every new environment — a staging copy, a customer's install — must be added to every
such branch. Each difference becomes a setting of its own — a URL, a flag, a limit — that the entry
point reads with the rest and hands in; nothing below the entry point reads the process environment.
The environment's name is metadata only: a resource attribute on traces and metrics, a log field.

**Example:**
```python
# WRONG — the sandbox is chosen by the environment's name, untested until production
def main() -> None:
    settings = Settings()
    if settings.environment == "production":
        gateway = CardGateway(base_url="https://api.payments.example.com")
    else:
        gateway = CardGateway(base_url="https://sandbox.payments.example.com")
    run_checkout(gateway=gateway)


# CORRECT — the difference is a setting of its own; every environment runs the same code
def main() -> None:
    settings = Settings()
    run_checkout(gateway=CardGateway(base_url=settings.payment_gateway_url))
```


### Tests never build `Settings`; they pass fields

**Why:** the test root builds the graph from literals. `Settings` itself is tested alone, with
`monkeypatch.setenv` and `delenv`, because a settings loader reads the environment even when it
skips the `.env` file — measured, a variable left in the shell filled a field the test never set.

**Example:**
```python
# WRONG — the test reads whatever the developer's shell and .env happen to hold
def test_rates_are_fetched_from_the_configured_url() -> None:
    settings = Settings(_env_file=None)
    fetcher = RateFetcher(
        client=RecordingClient(),
        rates_url=settings.rates_url,
        timeout_seconds=settings.rates_timeout_seconds,
    )


# CORRECT — literals, and nothing from the environment
def test_rates_are_fetched_from_the_configured_url() -> None:
    client = RecordingClient()
    fetcher = RateFetcher(client=client, rates_url="https://rates.example.com", timeout_seconds=5.0)

    fetcher.fetch()

    assert client.requested_urls == ["https://rates.example.com"]
```

## Startup and Secrets

### Configuration is validated at startup, before serving

**Why:** a missing or malformed variable then stops the process with a clear message, instead of
failing the first request hours later; a feature flag is a typed field read once and injected,
never queried deep in the call stack.

**Example:**
```python
# WRONG — read on first use: a misspelt variable name surfaces as a 500 on the first request
def rates_url() -> str:
    return os.environ["RATES_URL"]


# CORRECT — every field parsed and validated at once, when main() builds the settings
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Settings:
    rates_url: str
    rates_timeout_seconds: float
    reminders_enabled: bool

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> Self:
        timeout_seconds = float(environ["RATES_TIMEOUT_SECONDS"])
        if timeout_seconds <= 0:
            raise InvalidSettingError("RATES_TIMEOUT_SECONDS", timeout_seconds)
        return cls(
            rates_url=environ["RATES_URL"],
            rates_timeout_seconds=timeout_seconds,
            reminders_enabled=environ.get("REMINDERS_ENABLED") == "true",
        )
```

### A secret never appears in code, in a default or in a log

**Why:** a placeholder default lets a deploy that forgot the variable start and run with
`"changeme"`; a plain `str` secret is printed by the first `repr` of the settings.
