# Descriptions

### A description is what the skill does, then `Use when` and the signals a task contains

**Why:** the `description` is all the model sees of a skill until it decides to load it, among a
few dozen others. The signals are what a task actually contains — a library's import, `async def`, a
file name, "slow", "migration". A table of contents matches nothing, because the rules a skill holds
are not words a task contains, and it costs the listing, which Claude Code caps at 1% of the context
window and drops from the least-invoked skill first. `scripts/check_rules.py` holds every
description to 400 characters and a `Use when` clause; Anthropic's own examples are under 250.

**Example:**
```yaml
# WRONG — a table of contents, and the trigger last if at all
description: >-
  Covers keys, TTLs, jitter, stampedes, negative caching, locks, invalidation, serialization and
  testing of caches in Python services.

# CORRECT — what it does, then the signals a task contains
description: >-
  Designs caching whatever the library: keys, TTLs, stampedes, invalidation. Use when adding a
  cache, a memoized lookup or a TTL, or when a read is slow or a hot key is read by many requests.
```

### Neighbouring descriptions are told apart in their own words

**Why:** the listing is read as a whole, and a description that matches better than the right one
wins — on a public benchmark, wrong selection grew with the size of the library and caused most of
the loss. Two skills whose descriptions both match the same work load the same text twice. A topic
says it designs something "whatever the library"; a library skill starts with the library's name and
says it holds the mechanics behind the topic's contract.

**Example:**
```yaml
# WRONG — the library skill describes the topic, and both match every caching task
description: >-
  Caching in Python: keys, TTLs, stampedes and invalidation. Use when adding a cache.

# CORRECT — the library first, and the mechanics behind the topic's contract
description: >-
  redis-py mechanics behind the cache and lock contracts: clients, pools, Lua, pub/sub. Use when
  code imports redis or redis.asyncio, or configures a Redis connection.
```
