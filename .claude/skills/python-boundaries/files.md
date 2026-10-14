# Files

A file is a boundary too: another process reads it, possibly while it is being written, possibly on
a machine with another locale.

### A file someone else reads is replaced, never rewritten in place

**Why:** a crash or a full disk mid-write leaves a truncated file where a whole one stood. A
temporary file in the same directory, flushed to disk and moved over the target with `os.replace`,
shows a reader the old file or the new one, never half of either; the same directory matters,
because a rename is atomic only within one filesystem. `delete_on_close=False` (3.12) keeps the file
through `close()` and still removes it when anything fails before the rename.

**Example:**
```python
# WRONG — a departure board can open the timetable half written
def publish_timetable(path: Path, timetable: bytes) -> None:
    path.write_bytes(timetable)


# CORRECT — written beside the target, flushed to disk, then renamed over it in one step
def publish_timetable(path: Path, timetable: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", delete_on_close=False
    ) as temporary:
        temporary.write(timetable)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary.close()
        os.replace(temporary.name, path)
```
