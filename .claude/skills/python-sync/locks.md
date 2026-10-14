# Locks and Shared State

No shared state at all is better than any lock here: a thread that owns its data and hands results
over through a queue needs none. A lock shared with coroutines on a loop is `python-async`.

### State shared between threads is guarded by a `threading.Lock`; the GIL is not a lock

**Why:** a check-then-set on a shared dict races between threads today, and on a free-threaded
`3.13t` or `3.14t` build every compound operation does.

**Example:**
```python
# WRONG — two threads read the same count, and one finished encode is never counted
@final
class EncodeTally:
    def __init__(self) -> None:
        self._count_by_codec: dict[Codec, int] = {}

    def record(self, codec: Codec) -> None:
        self._count_by_codec[codec] = self._count_by_codec.get(codec, 0) + 1


# CORRECT — the read and the write happen under one lock
@final
class EncodeTally:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count_by_codec: dict[Codec, int] = {}

    def record(self, codec: Codec) -> None:
        with self._lock:
            self._count_by_codec[codec] = self._count_by_codec.get(codec, 0) + 1
```

### A lock covers the data, never the slow call that fills it

**Why:** a lock held across I/O makes every thread that wants any entry wait behind the slowest
probe. The probe runs outside; the lock covers the read and the write, and `setdefault` keeps the
first value if two threads probed at once.

**Example:**
```python
# WRONG — every thread asking for any duration waits behind one slow probe
@final
class SourceDurations:
    def __init__(self, *, prober: MediaProber) -> None:
        self._prober = prober
        self._lock = threading.Lock()
        self._seconds_by_source: dict[Path, float] = {}

    def duration_seconds(self, source: Path) -> float:
        with self._lock:
            if source not in self._seconds_by_source:
                self._seconds_by_source[source] = self._prober.probe_duration_seconds(source)
            return self._seconds_by_source[source]


# CORRECT — the lock covers the dictionary only; the probe runs outside it
@final
class SourceDurations:
    def __init__(self, *, prober: MediaProber) -> None:
        self._prober = prober
        self._lock = threading.Lock()
        self._seconds_by_source: dict[Path, float] = {}

    def duration_seconds(self, source: Path) -> float:
        with self._lock:
            cached = self._seconds_by_source.get(source)
        if cached is not None:
            return cached
        probed = self._prober.probe_duration_seconds(source)
        with self._lock:
            return self._seconds_by_source.setdefault(source, probed)
```

### `threading.local` is for per-thread resources only, and thread-safety is documented

**Why:** in async code many tasks share one thread, so a thread-local leaks between them —
`contextvars` is the per-task store. A thread-local fits a resource that must not cross threads, a
connection a non-thread-safe driver hands out. Whether a class may be shared between threads is a
property its docstring states, never an assumption its callers make.
