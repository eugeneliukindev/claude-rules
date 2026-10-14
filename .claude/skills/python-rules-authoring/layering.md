# One Rule, One Home

### A rule is written in exactly one file, and a skill never restates a rule file

**Why:** three copies of the retry policy drift into three policies; two files that disagree about
where a test fake lives get one of them followed at random. The rule files load on every `.py`, so
a skill assumes them: where it relies on one, it cites the file in a clause — "(`errors.md`)" — and
repeats none of it, and where a skill contradicts a rule, the rule wins and the skill is fixed.
Between two skills a rule has one owner; the other drops it, and a case where it differs is an
`**Except:**` of its own rule.

### A skill names a neighbour only in its introduction, once, as a route

**Why:** naming a skill does not load it — Anthropic's guidance says skills cannot reference each
other — so a "see python-x" inside a rule points the reader at text they do not have, and the
rule reads as incomplete. The introduction, between the title and the first heading below it,
routes work that started in the wrong skill; a carve-out is an `**Except:**` sentence in the rule it
qualifies. A library skill keeps `## With Other Libraries`, linking
`../python-integrations/<a>-<b>.md`. `scripts/check_rules.py` reports a skill named anywhere else.

### A topic skill is library-agnostic, and a library skill shows its own adapter

**Why:** the topic holds the design and the protocol's facts, with examples against contracts of its
own, so they hold whatever library serves them. The library skill holds its traps and every example
written in its API, against an adapter in its own domain with its own names: the topic's contract is
a concept the adapter matches, never a class the library skill implements or repeats — the pair
taught one cache, one verifier and one channel to every task that touched either. A library without
a skill goes to the library skill it runs under — Starlette, uvicorn and sse-starlette to
`python-fastapi` — or, while it earns only a line, stays in the topic as that line; it earns a skill
when its traps fill a screen.

**Example:**
```python
# WRONG — the library skill implements the topic skill's contract, names and all
@final
class RedisScheduleCache(ScheduleCache):
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    @override
    async def get(self, key: str) -> bytes | None:
        return await self._redis.get(key)


# CORRECT — an adapter of the library skill's own, in its own domain
@final
class BeaconScheduleStore:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def schedule_of(self, beacon_id: BeaconId) -> bytes | None:
        return await self._redis.get(f"beacon-schedule:{beacon_id}")
```

### A library's lifetime is the library's own context manager

**Why:** `python-wiring` once named a resource's context manager for its lifetime — `managed_pool` —
and every library skill repeated the shape with a wrapper of its own, `managed_redis`,
`managed_cashews`, `managed_grpc_server`; the model learned the prefix and wrapped libraries that
already had one. The root enters what the library ships — `async with asyncpg.create_pool(...)`,
`with niquests.Session()`, `async with broker:`. A hand-written `@contextmanager` or
`@asynccontextmanager` is for a library that has none, and is named for what it yields, never with
a fixed prefix.

**Example:**
```python
# WRONG — a wrapper around a context manager the library already has, under a house prefix
@asynccontextmanager
async def managed_survey_pool(*, dsn: str) -> AsyncIterator[asyncpg.Pool]:
    pool = await asyncpg.create_pool(dsn)
    try:
        yield pool
    finally:
        await pool.close()


# CORRECT — the root enters the library's own
async def main() -> None:
    settings = Settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        await serve_soundings(pool=pool)
```

### An example uses its own library and its own contracts, never another library's API

**Why:** the model copies examples, the surface included: a unit of work shown in eight skills and
an `AsyncSession` in the caching skill taught one storage design to every task that touched a cache,
a stream or a route. Each skill's examples run against contracts in its own domain — a
`KeeperRoster`, a `BeaconLog` — and only the library skill writes the library's calls. Where two
libraries really meet — SQLAlchemy in a FastAPI app, strawberry mounted in it — the seam is one
file for the pair, `python-integrations/<a>-<b>.md` with the names in alphabetical order, which
neither skill owns and both reach through the same "Before…" section under
`## With Other Libraries`, so the pair reads the same from either side; the directory is not a skill
and has no `SKILL.md`. Every other file shows no second library at all. `scripts/check_rules.py`
reports a library's API anywhere else, and a pair's file either skill does not link; alembic, built
on SQLAlchemy, is the one skill that speaks another's API throughout.

**Example:**
```python
# WRONG — the topic skill's example is written in SQLAlchemy
@final
class KeeperLookup:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory


# CORRECT — the topic skill's example knows only its own contracts
@final
class KeeperLookup:
    def __init__(self, *, keepers: KeeperRoster) -> None:
        self._keepers = keepers
```
