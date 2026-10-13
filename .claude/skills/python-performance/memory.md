# Memory

### Many numbers of one type are an `array`, not a list

**Why:** every element of a `list[int]` or `list[float]` is an object of its own behind a pointer;
`array("q")` and `array("d")` store eight bytes each in one buffer — a million latencies took 40 MB
as a list and 8 MB as an array. Arithmetic over whole columns is numpy's job, a dependency a
measurement decides.

### A large byte buffer is sliced through a `memoryview`, released with `with`

**Why:** slicing `bytes` copies; slicing a `memoryview` does not — cutting 50 MB into 64 KiB chunks
took 15.5 ms a pass as `bytes` slices and 0.2 ms as views, with no second copy alive. While a view
exists, the buffer under it cannot be resized or freed, so it is released with `with`.

**Example:**
```python
# WRONG — every chunk is a fresh 64 KiB copy
def write_in_chunks(payload: bytes, sink: BinaryIO) -> None:
    for offset in range(0, len(payload), _CHUNK_SIZE_BYTES):
        sink.write(payload[offset : offset + _CHUNK_SIZE_BYTES])


# CORRECT — the slices point into payload, and the view is released on the way out
def write_in_chunks(payload: bytes, sink: BinaryIO) -> None:
    with memoryview(payload) as view:
        for offset in range(0, len(view), _CHUNK_SIZE_BYTES):
            sink.write(view[offset : offset + _CHUNK_SIZE_BYTES])
```

### A class with fixed attributes has `__slots__`, and so does every base above it

**Why:** slots save memory per instance and speed attribute access, but one base without
`__slots__` gives every class below it a `__dict__` back, silently — a utility base once did. A
mixin declares `__slots__ = ()`, and multiple inheritance works when at most one base has non-empty
slots. `slotscheck` in the lint step finds both. Skipped only for dynamic attributes, a framework
that requires `__dict__`, and `cached_property`.

**Example:**
```python
# WRONG — the mixin has no __slots__, so every SensorReading carries a __dict__ anyway
class TimestampedMixin:
    def age_seconds(self, *, now_ns: int) -> float:
        return (now_ns - self.recorded_at_ns) / 1e9

    recorded_at_ns: int


@final
class SensorReading(TimestampedMixin):
    __slots__ = ("recorded_at_ns", "value")

    def __init__(self, *, recorded_at_ns: int, value: float) -> None:
        self.recorded_at_ns = recorded_at_ns
        self.value = value


# CORRECT — the mixin declares empty slots, and the instance has no __dict__
class TimestampedMixin:
    __slots__ = ()

    recorded_at_ns: int

    def age_seconds(self, *, now_ns: int) -> float:
        return (now_ns - self.recorded_at_ns) / 1e9


@final
class SensorReading(TimestampedMixin):
    __slots__ = ("recorded_at_ns", "value")

    def __init__(self, *, recorded_at_ns: int, value: float) -> None:
        self.recorded_at_ns = recorded_at_ns
        self.value = value
```
