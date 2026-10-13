# Stampede

When a hot key expires, every request in flight misses at once and each loads the same value.

### In one process, a miss for a key that is already loading awaits that load

**Why:** fifty concurrent misses for one profile are fifty loads from the database. The first miss
starts the load and later misses await the same task. `shield` keeps one caller's cancellation from
cancelling the load the others wait on; the dictionary holds the task, so it is never a dropped
`create_task` (`python-async`), and the done callback removes it, so the dictionary does not grow.

**Example:**
```python
# WRONG — every concurrent miss for one profile loads it again
@final
class ProfileLookup:
    def __init__(
        self, *, profiles: ProfileRepository, cache: Cache, ttl: timedelta = _PROFILE_TTL
    ) -> None:
        self._profiles = profiles
        self._cache = cache
        self._ttl = ttl

    async def find(self, user_id: UserId) -> Profile | None:
        payload = await self._cache.get(_profile_key(user_id))
        if payload is not None:
            return _profile_from_payload(payload)
        return await self._load_and_cache(user_id)

    async def _load_and_cache(self, user_id: UserId) -> Profile | None:
        profile = await self._profiles.find(user_id)
        if profile is not None:
            payload = _profile_to_payload(profile)
            await self._cache.set(_profile_key(user_id), payload, ttl=self._ttl)
        return profile


# CORRECT — the first miss loads; the others for the same user await the same task
@final
class ProfileLookup:
    def __init__(
        self, *, profiles: ProfileRepository, cache: Cache, ttl: timedelta = _PROFILE_TTL
    ) -> None:
        self._profiles = profiles
        self._cache = cache
        self._ttl = ttl
        self._loads_in_flight: dict[UserId, asyncio.Task[Profile | None]] = {}

    async def find(self, user_id: UserId) -> Profile | None:
        payload = await self._cache.get(_profile_key(user_id))
        if payload is not None:
            return _profile_from_payload(payload)
        load = self._loads_in_flight.get(user_id)
        if load is None:
            load = asyncio.create_task(self._load_and_cache(user_id))
            self._loads_in_flight[user_id] = load
            load.add_done_callback(lambda _: self._loads_in_flight.pop(user_id, None))
        return await asyncio.shield(load)

    async def _load_and_cache(self, user_id: UserId) -> Profile | None:
        profile = await self._profiles.find(user_id)
        if profile is not None:
            payload = _profile_to_payload(profile)
            await self._cache.set(_profile_key(user_id), payload, ttl=self._ttl)
        return profile
```

### Across processes, a hot and expensive key is refreshed before it expires, by one caller

**Why:** single-flight still leaves one load per worker, and a jittered TTL only spreads keys that
were written together. For a key both hot and expensive, the payload records when it was computed;
once it is past a fraction of the TTL, the one caller whose `add` on a refresh marker answers `True`
recomputes, while everyone else is served the current value. The marker is an efficiency lock
([locks.md](locks.md)).

**Example:**
```python
# WRONG — the leaderboard expires everywhere at once, and every worker recomputes it
async def leaderboard(*, cache: Cache, scores: ScoreBoard) -> Leaderboard:
    payload = await cache.get(_LEADERBOARD_KEY)
    if payload is not None:
        return _leaderboard_from_payload(payload)
    board = await scores.compute_leaderboard()
    await cache.set(_LEADERBOARD_KEY, _leaderboard_to_payload(board), ttl=_LEADERBOARD_TTL)
    return board


# CORRECT — past most of its life, one caller refreshes it; the rest keep reading the old one
async def leaderboard(*, cache: Cache, scores: ScoreBoard, clock: Clock) -> Leaderboard:
    payload = await cache.get(_LEADERBOARD_KEY)
    if payload is None:
        return await _recompute(cache=cache, scores=scores, clock=clock)
    cached = _leaderboard_from_payload(payload)
    is_ageing = clock.now() - cached.computed_at > _LEADERBOARD_TTL * _REFRESH_AFTER_FRACTION
    if is_ageing and await cache.add(_LEADERBOARD_REFRESH_KEY, b"", ttl=_REFRESH_MARKER_TTL):
        return await _recompute(cache=cache, scores=scores, clock=clock)
    return cached
```
