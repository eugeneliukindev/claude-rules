# Settings

Where settings are built and how their fields are passed is `python-wiring`.

### `BaseSettings` is built once at the root, validated at startup, with credentials as `SecretStr`

**Why:** settings are a boundary model like any other — constructed once in the composition root and
passed down, never a module-level singleton — and a missing variable crashes the process at start,
not on the first request that touches it. A credential is `SecretStr` or `SecretBytes`, which render
as `'**********'`, so a stray `repr`, traceback or debug log cannot print it; `get_secret_value()`
is the one place it is read. `_env_file=None` skips the `.env` file but still reads the environment
— measured on pydantic-settings 2.15 — so a test of `Settings` clears what it leaves unset.

**Example:**
```python
# WRONG — repr(settings), a traceback or a debug log prints the key in full
@final
class Settings(BaseSettings):
    catalog_api_key: str


# CORRECT — renders as '**********'; get_secret_value() is the one place it is read
@final
class Settings(BaseSettings):
    catalog_api_key: SecretStr
```

### Settings classes that share one `.env` file each set `extra="ignore"`

**Why:** `BaseSettings` forbids extra input, and every line of its `env_file` is input to it —
measured on pydantic-settings 2.15, a `ServerSettings` and an `AppSettings` reading one file each
failed on the other's lines with `Extra inputs are not permitted`, with an `env_prefix` or without.
The environment is never checked for extras, so a class read from the environment alone keeps the
default.

**Example:**
```python
# WRONG — each class rejects the other's lines in the shared file
@final
class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    host: str
    port: int


# CORRECT — each reads its own fields from the file and leaves the rest
@final
class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str
    port: int
