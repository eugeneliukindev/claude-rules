# Negative Caching

### Whether absence is cached is decided per kind, with its own shorter TTL

**Why:** without it, every request for an id that does not exist reaches the database, and a caller
enumerating ids is a load test. With it, absence is a payload of its own — `null`, which the
payload reader turns back into `None` — under a TTL as short as a caller may wait for a new entity
to appear, and the path that creates the entity deletes that key after its commit, which the shared
key function makes one line. Left to what a decorator happens to do, it is a decision nobody made.
