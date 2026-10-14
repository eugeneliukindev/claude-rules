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
async def register_json_codecs(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.set_type_codec(
            "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads
        )


# CORRECT — every connection the pool opens is initialised the same way
async def _register_json_codecs(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads
    )


def tournament_pool(dsn: str, *, max_connections: int = _MAX_CONNECTIONS) -> asyncpg.Pool:
    return asyncpg.create_pool(dsn, max_size=max_connections, init=_register_json_codecs)
```
