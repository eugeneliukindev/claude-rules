# Settings and Startup

The composition root and resource lifetime are in `SKILL.md`; the settings model in pydantic is
`python-pydantic`, and FastAPI's form of the settings accessor is `python-fastapi`.

## Contents

- Configuration is one typed settings object, built once at the root and passed in
- Pass fields, never the configuration root
- Tests never build `Settings`; they pass fields
- Configuration is validated at startup, before serving
- A secret never appears in code, in a default or in a log

## The Settings Object

### Configuration is one typed settings object, built once at the root and passed in

**Why:** anything that varies by environment read from `os.environ` across the code is a dependency
nobody declared; a module-level settings instance — or a cached `get_settings()`, the `@lru_cache`
getter FastAPI's documentation teaches — is that instance by another name, global, and changed in a
test only through `cache_clear()` and the environment.

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

### Pass fields, never the configuration root

**Why:** middleware that kept the settings object it was given changed behaviour when someone edited
that object after startup; fields copied at construction cannot. The signature of a function taking
`settings: Settings` stops being a dependency list, and a test has to build the whole tree for one
call — an untyped `**kwargs` has the same defect. Unpacking happens once, in the root.

**Example:**
```python
# WRONG — the signature hides what is read, and a test builds every settings group for one call
@final
class RateFetcher:
    def __init__(self, *, client: HttpClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    def fetch(self) -> RateTable:
        return self._client.get_rates(
            self._settings.rates_url, timeout_seconds=self._settings.rates_timeout_seconds
        )


# CORRECT — the signature is the dependency list; the root unpacks the settings
@final
class RateFetcher:
    def __init__(self, *, client: HttpClient, rates_url: str, timeout_seconds: float) -> None:
        self._client = client
        self._rates_url = rates_url
        self._timeout_seconds = timeout_seconds

    def fetch(self) -> RateTable:
        return self._client.get_rates(self._rates_url, timeout_seconds=self._timeout_seconds)
```

### Tests never build `Settings`; they pass fields

**Why:** the test root builds the graph from literals. `Settings` itself is tested alone, with
`monkeypatch.setenv` and `delenv` — `_env_file=None` skips the `.env` file but still reads the
environment; measured on pydantic-settings 2.15, a variable left in the shell filled a field the
test never set.

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

**Example:**
```python
# WRONG — a placeholder default, and a repr that prints the password
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Settings:
    database_password: str = "changeme"


# CORRECT — no default, so a forgotten variable stops the start; and kept out of every repr
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Settings:
    database_password: str = field(repr=False)
```
