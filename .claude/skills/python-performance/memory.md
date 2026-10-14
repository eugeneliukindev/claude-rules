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
def write_packed_rolls(
    packed_rolls: bytes, sink: BinaryIO, *, chunk_size_bytes: int = _CHUNK_SIZE_BYTES
) -> None:
    for offset in range(0, len(packed_rolls), chunk_size_bytes):
        sink.write(packed_rolls[offset : offset + chunk_size_bytes])


# CORRECT — the slices point into packed_rolls, and the view is released on the way out
def write_packed_rolls(
    packed_rolls: bytes, sink: BinaryIO, *, chunk_size_bytes: int = _CHUNK_SIZE_BYTES
) -> None:
    with memoryview(packed_rolls) as view:
        for offset in range(0, len(view), chunk_size_bytes):
            sink.write(view[offset : offset + chunk_size_bytes])
```

### A class with fixed attributes has `__slots__`, and so does every base above it

**Why:** slots save memory per instance and speed attribute access, but one base without
`__slots__` gives every class below it a `__dict__` back, silently — a utility base once did. A
mixin declares `__slots__ = ()`, and multiple inheritance works when at most one base has non-empty
slots. `slotscheck` in the lint step finds both. Skipped only for dynamic attributes, a framework
that requires `__dict__`, and `cached_property`.

**Example:**
```python
# WRONG — the mixin has no __slots__, so every Die carries a __dict__ anyway
class FacesMixin:
    faces: int

    def highest_total(self, *, dice: int) -> int:
        return self.faces * dice


@final
class Die(FacesMixin):
    __slots__ = ("faces", "label")

    def __init__(self, *, faces: int, label: str) -> None:
        self.faces = faces
        self.label = label


# CORRECT — the mixin declares empty slots, and the instance has no __dict__
class FacesMixin:
    __slots__ = ()

    faces: int

    def highest_total(self, *, dice: int) -> int:
        return self.faces * dice


@final
class Die(FacesMixin):
    __slots__ = ("faces", "label")

    def __init__(self, *, faces: int, label: str) -> None:
        self.faces = faces
        self.label = label
```
