# One Rule, One Home

### A rule is written in exactly one file, and every other file points to it

**Why:** three copies of the retry policy drift into three policies; two files that disagree about
where a test fake lives get one of them followed at random. Naming a skill does not load it —
Anthropic's guidance says skills cannot reference each other — so a skill that relies on a rule
homed elsewhere states it as one imperative line and points home for the reason, the examples and
the carve-outs. One line is the ceiling.

**Example:**
```markdown
<!-- WRONG — a bare reference: a task that never opens the other skill never gets the rule -->
Cache failures are covered in `python-caching`.

<!-- CORRECT — the rule in one line, and where its reason lives -->
A cache failure is a counted miss, never an error (why and how: `python-caching`).
```

### A topic skill is library-agnostic, and a library's mechanics and examples live in its own skill

**Why:** the topic holds the design and the protocol's facts, with examples against the
application's own contracts — a `Cache`, a `TokenVerifier`, a `send` callable — so they hold
whatever library implements them. The library skill implements those contracts and holds its traps
and every example written in its API: `python-caching` and `python-redis`, `python-persistence` and
`python-sqlalchemy`. A library without a skill goes to the library skill it runs under — Starlette,
uvicorn and sse-starlette to `python-fastapi` — or, while it earns only a line, stays in the topic
as that line; it earns a skill when its traps fill a screen.

**Example:**
```python
# WRONG — a topic's example written against one library's client
async def cached_profile(redis: Redis, user_id: UserId) -> Profile | None:
    raw = await redis.get(f"profile:{user_id}")
    return None if raw is None else Profile.model_validate_json(raw)


# CORRECT — against the application's contract, which any library can implement
async def cached_profile(cache: Cache, user_id: UserId) -> Profile | None:
    raw = await cache.get(f"profile:{user_id}")
    return None if raw is None else Profile.model_validate_json(raw)
```

### A topic names a library skill only in a file's introduction, once, as a route

**Why:** work that starts from the design still finds the library's traps, while the rules, their
reasons and their examples hold for any library. A library skill points back to the topic for the
reason as often as it needs. `scripts/check_rules.py` reports a topic file that names a library
skill after its first heading below the title.

**Example:**
```markdown
<!-- WRONG — a library skill named inside a rule's reason -->
**Why:** a lock without a TTL outlives a crashed holder; `python-redis` sets it with `SET NX PX`.

<!-- CORRECT — the route in the introduction, before the first heading -->
# Caching

The redis implementation is `python-redis`, the decorator layer `python-cashews`.
```

### An example uses its own library and the application's contracts, never another library's API

**Why:** the model copies examples, the surface included: a unit of work shown in eight skills and
an `AsyncSession` in the caching skill taught one storage design to every task that touched a cache,
a stream or a route. Each skill's examples run against contracts in its own domain — a
`ProfileRepository`, a `ParcelHistory`, a `ConnectionPool` — and only the library skill writes the
library's calls. `scripts/check_rules.py` reports a library's API in any other file's example,
except where one library is built on another — alembic on SQLAlchemy, strawberry on FastAPI — the
pairs it lists as integrations.

**Example:**
```python
# WRONG — the caching skill's example is written in SQLAlchemy
@final
class ProfileLookup:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession], cache: Cache) -> None:
        self._session_factory = session_factory
        self._cache = cache


# CORRECT — the caching skill's example knows only its own contracts
@final
class ProfileLookup:
    def __init__(self, *, profiles: ProfileRepository, cache: Cache) -> None:
        self._profiles = profiles
        self._cache = cache
```
