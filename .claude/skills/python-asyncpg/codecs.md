# JSON and Other Codecs

### A type codec is registered in the pool's `init`, on `pg_catalog`

**Why:** `json` and `jsonb` arrive as `str`, and a `dict` passed for one raises `DataError`. A codec
converts both ways, and it is registered per connection — so in the pool's `init`, which runs on
every connection the pool opens, replacements included; registered once at startup, the other
connections still return `str`. The types live in `pg_catalog`, and the default `schema="public"`
fails with `unknown type: public.jsonb`. The default codec format is text, so the encoder returns
`str` — an encoder that produces `bytes` is decoded here. `setup=` runs on every acquire and is not
for codecs.

**Example:**
```python
# WRONG — registered on one connection at startup: the others still return jsonb as str
async def prepare_pool(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.set_type_codec(
            "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads
        )


# CORRECT — every connection the pool opens is initialised the same way
async def _register_json_codecs(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads
    )


@asynccontextmanager
async def managed_pool(settings: DatabaseSettings) -> AsyncIterator[asyncpg.Pool]:
    async with asyncpg.create_pool(
        settings.url,
        min_size=settings.min_connections,
        max_size=settings.max_connections,
        command_timeout=settings.command_timeout_seconds,
        init=_register_json_codecs,
    ) as pool:
        yield pool
```
