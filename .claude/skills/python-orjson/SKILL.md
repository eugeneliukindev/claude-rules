---
name: python-orjson
description: >-
  orjson mechanics: bytes in and out, options for keys and ordering, a default= that raises, NaN
  written as null, Decimal refused. Use when code imports orjson or serializes a payload with it.
  Not for what a payload may contain (python-boundaries).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# orjson

Checked against orjson 3.13. It serializes `datetime`, `UUID`, dataclass and enum values without a
hand-written encoder, and faster than `json`; `Decimal` it refuses with `TypeError`. What a payload
may contain, and that a parsed one is still validated, is `python-boundaries`.

### `dumps` returns `bytes` and `loads` takes `bytes`; nothing is decoded on the way

**Why:** a reflexive `.decode()` that the next layer encodes again is a round trip that buys
nothing; decoding happens only where a `str` is genuinely required — a response body, a database
column, a log line. A frozen dataclass, its `datetime`, `UUID` and enum fields included, goes to
`dumps` as it is.

**Example:**
```python
# WRONG — decoded to str only for the feed to encode it again, and decoded again to parse
def publish_logged_run(run: LoggedRun, *, feed: RunFeed) -> None:
    feed.send(orjson.dumps(run).decode())


def read_logged_run(body: bytes) -> object:
    return orjson.loads(body.decode())


# CORRECT — bytes out, bytes in
def publish_logged_run(run: LoggedRun, *, feed: RunFeed) -> None:
    feed.send(orjson.dumps(run))


def read_logged_run(body: bytes) -> object:
    return orjson.loads(body)
```

### A number is checked for `NaN` and infinity where it is parsed: orjson writes them as `null`

**Why:** `orjson.dumps(float("nan"))` is `b"null"`, and so is infinity — no error, where `json`
writes `NaN` — so a bad number ships as "no value" and the consumer cannot tell the two apart.
`float()` accepts `"nan"` and `"inf"`.

**Example:**
```python
# WRONG — a "nan" in the watch export ships as null, and the consumer reads "no heart rate"
def encode_lap(raw_heart_rate_bpm: str) -> bytes:
    return orjson.dumps({"heart_rate_bpm": float(raw_heart_rate_bpm)})


# CORRECT — the number is checked where it is parsed; orjson would not refuse it
def encode_lap(raw_heart_rate_bpm: str) -> bytes:
    heart_rate_bpm = float(raw_heart_rate_bpm)
    if not math.isfinite(heart_rate_bpm):
        raise InvalidLapError(raw_heart_rate_bpm)
    return orjson.dumps({"heart_rate_bpm": heart_rate_bpm})
```

### Output that is compared, hashed or kept in a fixture sets `OPT_SORT_KEYS`

**Why:** keys come out in insertion order, so two equal payloads can hash differently and a diff
means nothing. The other options are explicit too: `OPT_NON_STR_KEYS` for a mapping keyed by
anything but `str` — orjson raises rather than stringifying; `OPT_OMIT_MICROSECONDS` only when the
consumer's format demands it; never `OPT_NAIVE_UTC` in place of an aware datetime fixed at its
source.

**Example:**
```python
# WRONG — insertion order: equal plans can produce different digests
def training_plan_digest(plan: Mapping[str, object]) -> str:
    return hashlib.sha256(orjson.dumps(plan)).hexdigest()


# CORRECT — sorted keys, nested ones included: equal plans give equal bytes
def training_plan_digest(plan: Mapping[str, object]) -> str:
    return hashlib.sha256(orjson.dumps(plan, option=orjson.OPT_SORT_KEYS)).hexdigest()
```

### `default=` handles named types and raises `TypeError` for everything else

**Why:** a `default=str` serializes a stray object as its `str()` instead of failing, and ships a
bug. The escape hatch knows a few types — `Decimal` as a string — and raises for the rest; a type
orjson does not know is converted where the payload is built, not taught to a `default` that grows
to know every type.

**Example:**
```python
# WRONG — anything is accepted, so a stray object ships as its str() instead of failing
def encode_shoe_mileage(mileage: Mapping[str, object]) -> bytes:
    return orjson.dumps(mileage, default=str)


# CORRECT — Decimal becomes a string; anything else still raises TypeError
def _encode_decimal(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def encode_shoe_mileage(mileage: Mapping[str, object]) -> bytes:
    return orjson.dumps(mileage, default=_encode_decimal)
```
