# orjson

Not loaded automatically — open it when the code imports `orjson`.

## Why It Is Here

Speed, and correctness the standard library does not give: `datetime`, `UUID`, `Decimal`,
`dataclass` and `numpy` shapes serialize without a hand-written encoder. Reach for it in services;
the standard `json` is fine in a throwaway script.

## The Two Facts That Trip Everyone

- **`orjson.dumps` returns `bytes`, not `str`.** Decode only where a `str` is genuinely required —
  a response body, a database column, a log line. Writing `.decode()` reflexively and then
  re-encoding on the way out is a round trip that buys nothing.
- **`orjson.loads` accepts `bytes` directly.** Do not decode a response body to `str` first; hand it
  the bytes.

## Options Are Explicit

- **`OPT_NON_STR_KEYS`** when a mapping is keyed by anything other than `str` — otherwise it raises
  rather than silently stringifying, which is the right default and a surprise the first time.
- **`OPT_SORT_KEYS`** wherever the output is compared, hashed, or checked into a fixture. Unsorted
  keys make a diff meaningless and a content hash unstable.
- **`OPT_OMIT_MICROSECONDS`** only when the consumer's format demands it; otherwise keep the
  precision you were given.
- **Never `OPT_NAIVE_UTC` as a substitute for aware datetimes.** Fix the datetime at its source; the
  option papers over a value that was already wrong.

## Custom Types

- **`default=` is the one escape hatch**, and it is a function that raises `TypeError` for anything
  it does not know. A `default` that returns `str(obj)` for the unknown case will happily serialize a
  bug.
- Prefer making the type serializable at the boundary — a `to_dict()` on the value object — over
  growing a `default` that knows about every type in the codebase. That function is a generically
  named unit accumulating concrete knowledge.

## What It Does Not Change

- **Serialization still lives at the boundary.** Never serialize a domain or ORM object directly,
  whatever the encoder can technically handle: what it can reach, it will publish.
- **Untrusted input is still validated after parsing.** `loads` gives you a shape, not a contract.
