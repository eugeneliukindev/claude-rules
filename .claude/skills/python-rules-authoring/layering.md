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
qualifies. `scripts/check_rules.py` reports a skill named anywhere else.

### A library's lifetime is the library's own context manager

**Why:** `python-wiring` once named a resource's context manager for its lifetime — `managed_pool` —
and the skills of the time repeated the shape with a wrapper of their own, `managed_redis`,
`managed_grpc_server`; the model learned the prefix and wrapped libraries that already had one. The
root enters what the library ships — `async with asyncpg.create_pool(...)`, `async with broker:`. A
hand-written `@contextmanager` or `@asynccontextmanager` is for a library that has none, and is
named for what it yields, never with a fixed prefix.

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

### An example is written against its own contracts, never a library's API

**Why:** the model copies examples, the surface included: a unit of work shown in eight skills and
an `AsyncSession` in the caching skill taught one storage design to every task that touched a cache,
a stream or a route. Each skill's examples run against contracts in its own domain — a
`KeeperRoster`, a `BeaconLog` — so they hold whatever library serves them, and a library's own
calls come from its current documentation (`placement.md`). `scripts/check_rules.py` reports the
API of the libraries it knows inside any example.

**Example:**
```python
# WRONG — the skill's example is written in SQLAlchemy
@final
class KeeperLookup:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory


# CORRECT — the skill's example knows only its own contracts
@final
class KeeperLookup:
    def __init__(self, *, keepers: KeeperRoster) -> None:
        self._keepers = keepers
```
