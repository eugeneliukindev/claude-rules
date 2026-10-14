# Settings and Startup

Below the root nothing takes the settings object (`functions.md`).

## Contents

- Configuration is typed settings, built once at the root and unpacked there
- The server's settings are a class apart from the application's
- Behaviour never branches on the deployment environment's name
- Configuration is validated at startup, before serving
- A secret never appears in code, in a default or in a log

## The Settings Object

### Configuration is typed settings, built once at the root and unpacked there

**Why:** anything that varies by environment read from `os.environ` across the code is a dependency
nobody declared; a cached accessor behind `@lru_cache` is a module-level instance by another name,
global, and changed in a test only through `cache_clear()` and the environment.

**Example:**
```python
# WRONG — a global behind a function: every caller reaches it, and no test can hand in another
@lru_cache
def loan_settings() -> Settings:
    return Settings()


def fetch_insured_value(exhibit_id: ExhibitId, *, valuations: ValuationClient) -> Decimal:
    settings = loan_settings()
    return valuations.insured_value(exhibit_id, currency=settings.insurance_currency)


# CORRECT — built once by the root, which unpacks the fields each part needs
def fetch_insured_value(
    exhibit_id: ExhibitId, *, valuations: ValuationClient, currency: str
) -> Decimal:
    return valuations.insured_value(exhibit_id, currency=currency)


def main() -> None:
    settings = Settings()
    with ValuationClient(base_url=settings.valuation_url) as valuations:
        for exhibit_id in read_exhibit_ids(sys.stdin):
            insured_value = fetch_insured_value(
                exhibit_id, valuations=valuations, currency=settings.insurance_currency
            )
            print_insurance_certificate(exhibit_id, insured_value=insured_value)
```

### The server's settings are a class apart from the application's

**Why:** the host, the port and the drain configure the process that serves; the registry URL and
the limits configure what it serves. One class holding both makes every entry point supply all of
it — a worker running the same use cases cannot start without a port it never binds — and lets the
application's fields grow server knobs. Each entry point builds the classes of the parts it runs.

**Example:**
```python
# WRONG — one class: the worker needs HOST and PORT set before it starts
def serve_main() -> None:
    settings = Settings()
    serve_http(
        build_loan_api(registry_url=settings.registry_url), host=settings.host, port=settings.port
    )


def worker_main() -> None:
    settings = Settings()
    run_loan_worker(registry_url=settings.registry_url)


# CORRECT — each entry point builds what it runs, and the worker knows nothing of the server
def serve_main() -> None:
    listener_settings = ListenerSettings()
    registry_settings = LoanRegistrySettings()
    serve_http(
        build_loan_api(registry_url=registry_settings.registry_url),
        host=listener_settings.host,
        port=listener_settings.port,
    )


def worker_main() -> None:
    registry_settings = LoanRegistrySettings()
    run_loan_worker(registry_url=registry_settings.registry_url)
```

### Behaviour never branches on the deployment environment's name; each difference is a setting

**Why:** `if environment == "production"` is code that runs for the first time in the environment it
guards, and every new environment — a staging copy, a customer's install — must be added to every
such branch. Each difference becomes a setting of its own — a URL, a flag, a limit — that the entry
point reads with the rest and hands in. The environment's name is metadata only: a resource
attribute on traces and metrics, a log field.

**Example:**
```python
# WRONG — the sandbox is chosen by the environment's name, untested until production
def main() -> None:
    settings = Settings()
    if settings.environment == "production":
        insurer = TransitInsurer(base_url="https://api.insurer.example.com")
    else:
        insurer = TransitInsurer(base_url="https://sandbox.insurer.example.com")
    run_loan_intake(insurer=insurer)


# CORRECT — the difference is a setting of its own; every environment runs the same code
def main() -> None:
    settings = Settings()
    run_loan_intake(insurer=TransitInsurer(base_url=settings.insurer_url))
```

## Startup and Secrets

### Configuration is validated at startup, before serving

**Why:** a missing or malformed variable then stops the process with a clear message, instead of
failing the first request hours later; a feature flag is a typed field read once and injected,
never queried deep in the call stack. The settings class is tested alone, with
`monkeypatch.setenv` and `delenv`: a loader reads the environment even when it skips the `.env`
file — measured, a variable left in the shell filled a field the test never set.

**Example:**
```python
# WRONG — read on first use: a misspelt variable name surfaces as a 500 on the first request
def insurer_url() -> str:
    return os.environ["INSURER_URL"]


# CORRECT — every field parsed and validated at once, when main() builds the settings
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Settings:
    insurer_url: str
    valuation_timeout_seconds: float
    courier_tracking_enabled: bool

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> Self:
        timeout_seconds = float(environ["VALUATION_TIMEOUT_SECONDS"])
        if timeout_seconds <= 0:
            raise InvalidLoanSettingError("VALUATION_TIMEOUT_SECONDS", timeout_seconds)
        return cls(
            insurer_url=environ["INSURER_URL"],
            valuation_timeout_seconds=timeout_seconds,
            courier_tracking_enabled=environ.get("COURIER_TRACKING_ENABLED") == "true",
        )
```

### A secret never appears in code, in a default or in a log

**Why:** a placeholder default lets a deploy that forgot the variable start and run with
`"changeme"`; a plain `str` secret is printed by the first `repr` of the settings.
