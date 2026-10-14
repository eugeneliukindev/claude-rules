---
name: python-async
description: >-
  Writes asyncio code that never blocks the loop, holds every task, sizes its queues and cleans up
  on cancellation. Use when writing async def, awaiting I/O, using create_task, gather, TaskGroup,
  asyncio.timeout, a queue or anyio, or handing work from a coroutine to a thread or a process
  pool. Not for threads or pools without a loop (python-sync).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Asyncio

The mechanics of asyncio; the bound on a fan-out and the run's deadline are `principles.md`.
Testing coroutines — the plugin, its mode and loop scope — is `python-pytest`; threads and process
pools without a loop are `python-sync`; a response that lives for minutes is `python-streaming`.

## Deadlines

### One `asyncio.timeout` scope bounds a sequence of awaits; `wait_for` bounds one

**Why:** two `wait_for` calls in sequence each get the whole budget, so the caller waits twice as
long as it was promised; one scope bounds every await in its block, and `timeout_at` shares one
deadline between scopes. A client's own configured timeout is the bound for a single call.

### A deadline on blocking work lives in the blocking client, not around `to_thread`

**Why:** a thread cannot be cancelled. `asyncio.timeout` around `to_thread` stops the waiting; the
call runs to completion and keeps its executor slot, so a handful of hung calls exhausts the pool.

**Example:**
```python
# WRONG — the caller gets TimeoutError, and the hung download keeps its worker thread regardless
async def download_scene(
    scene_id: SceneId, *, mirror: SceneMirror, timeout_seconds: float = _DOWNLOAD_TIMEOUT_SECONDS
) -> bytes:
    async with asyncio.timeout(timeout_seconds):
        return await asyncio.to_thread(mirror.download, scene_id)


# CORRECT — the blocking client enforces the deadline, so the thread itself gives up
async def download_scene(
    scene_id: SceneId, *, mirror: SceneMirror, timeout_seconds: float = _DOWNLOAD_TIMEOUT_SECONDS
) -> bytes:
    return await asyncio.to_thread(mirror.download, scene_id, timeout_seconds=timeout_seconds)
```

## Tasks

### Concurrent tasks run in a `TaskGroup`, a fan-out under a semaphore; a bare `create_task` never

**Why:** a task nobody holds can be garbage-collected mid-flight and its exception silently lost.
The group holds every task, waits for all, cancels the siblings at the first failure and raises
the failures together. `asyncio.gather` with its default raises the first failure and leaves the
siblings running with nobody awaiting them — measured, the sibling ran to the end and printed;
`return_exceptions=True` is right only where a partial result is the contract, with every element
checked before use.

**Example:**
```python
# WRONG — nothing holds either task, and the caller never learns that one failed
async def publish_scene(scene: Scene, *, catalogue: SceneCatalogue, previews: PreviewTiler) -> None:
    asyncio.create_task(catalogue.index(scene))
    asyncio.create_task(previews.cut(scene))


# CORRECT — the group holds both, waits for both, and raises their failures together
async def publish_scene(scene: Scene, *, catalogue: SceneCatalogue, previews: PreviewTiler) -> None:
    async with asyncio.TaskGroup() as group:
        group.create_task(catalogue.index(scene))
        group.create_task(previews.cut(scene))


# CORRECT — a fan-out over a collection: the semaphore bounds what is in flight, one deadline the run
async def fetch_footprints(
    scene_ids: Sequence[SceneId],
    *,
    archive: SceneArchive,
    max_in_flight: int = _MAX_IN_FLIGHT,
    deadline_seconds: float = _FOOTPRINTS_DEADLINE_SECONDS,
) -> dict[SceneId, Footprint]:
    in_flight = asyncio.Semaphore(max_in_flight)

    async def fetch_one(scene_id: SceneId) -> Footprint:
        async with in_flight:
            return await archive.footprint(scene_id)

    async with asyncio.timeout(deadline_seconds), asyncio.TaskGroup() as group:
        tasks = {scene_id: group.create_task(fetch_one(scene_id)) for scene_id in scene_ids}
    return {scene_id: task.result() for scene_id, task in tasks.items()}
```

### A `TaskGroup`'s failures are caught with `except*`

**Why:** the group raises an `ExceptionGroup`, so a plain `except` clause never matches and the
failure escapes; flattening to the first exception loses the rest. Cancelling the task that owns
the group raises `CancelledError`, not an `ExceptionGroup`, and an `except*` for the children's
failures does not see it.

**Example:**
```python
# WRONG — a TaskGroup raises ExceptionGroup, so this clause never matches and the failure escapes
async def plan_passes(stations: Sequence[GroundStation], *, schedule: PassSchedule) -> None:
    try:
        async with asyncio.TaskGroup() as group:
            for station in stations:
                group.create_task(schedule.refresh(station))
    except StationUnreachableError:
        logger.warning("pass plan incomplete")


# CORRECT — except* matches inside the group, however many stations failed
async def plan_passes(stations: Sequence[GroundStation], *, schedule: PassSchedule) -> None:
    try:
        async with asyncio.TaskGroup() as group:
            for station in stations:
                group.create_task(schedule.refresh(station))
    except* StationUnreachableError as failures:
        logger.warning("pass plan incomplete", extra={"failed_stations": len(failures.exceptions)})
```

### A queue between tasks has a `maxsize`, and its producer ends it with `shutdown()`

**Why:** an unbounded queue lets a fast producer hold its whole backlog in memory; `maxsize` makes
`put` wait until the consumer catches up. `shutdown()` (3.13) ends the queue — `put` raises
`QueueShutDown` at once, `get` once the queue is drained — so no sentinel is put per consumer; on a
3.12 floor, one sentinel per consumer.

**Example:**
```python
# WRONG — downloads outrun tiling, and every scene waits in memory
async def tile_scenes(
    scene_ids: Sequence[SceneId], *, archive: SceneArchive, tiler: SceneTiler
) -> None:
    downloaded = asyncio.Queue[Scene]()
    async with asyncio.TaskGroup() as group:
        group.create_task(_cut_downloaded(downloaded, tiler=tiler))
        for scene_id in scene_ids:
            await downloaded.put(await archive.download(scene_id))
        downloaded.shutdown()


# CORRECT — at most max_pending_scenes wait; the consumer ends once the queue is shut and drained
async def tile_scenes(
    scene_ids: Sequence[SceneId],
    *,
    archive: SceneArchive,
    tiler: SceneTiler,
    max_pending_scenes: int = _MAX_PENDING_SCENES,
) -> None:
    downloaded = asyncio.Queue[Scene](maxsize=max_pending_scenes)
    async with asyncio.TaskGroup() as group:
        group.create_task(_cut_downloaded(downloaded, tiler=tiler))
        for scene_id in scene_ids:
            await downloaded.put(await archive.download(scene_id))
        downloaded.shutdown()


async def _cut_downloaded(downloaded: asyncio.Queue[Scene], *, tiler: SceneTiler) -> None:
    while True:
        try:
            scene = await downloaded.get()
        except asyncio.QueueShutDown:
            return
        await tiler.cut(scene)
```

## Cancellation

### Cancellation is cleaned up after and re-raised, never swallowed

**Why:** swallowed, an enclosing timeout or `TaskGroup` sees a normal return and carries on.
`CancelledError` is a `BaseException`, so `except Exception` lets it through by design, and
`except BaseException` "for resilience" swallows it. Shielding is reserved for a commit that must
finish, always under a timeout of its own.

**Example:**
```python
# WRONG — swallowed: whoever cancelled this task believes it finished normally
async def await_downlink(
    pass_id: PassId, *, station: GroundStation, poll_seconds: float = _DOWNLINK_POLL_SECONDS
) -> None:
    try:
        while not await station.is_downlinked(pass_id):
            await asyncio.sleep(poll_seconds)
    except asyncio.CancelledError:
        logger.info("downlink wait stopped", extra={"pass_id": pass_id})


# CORRECT — the stop is recorded, and the cancellation travels on to whoever asked for it
async def await_downlink(
    pass_id: PassId, *, station: GroundStation, poll_seconds: float = _DOWNLINK_POLL_SECONDS
) -> None:
    try:
        while not await station.is_downlinked(pass_id):
            await asyncio.sleep(poll_seconds)
    except asyncio.CancelledError:
        logger.info("downlink wait stopped", extra={"pass_id": pass_id})
        raise
```

### An async generator left early is closed with `aclosing`

**Why:** left open, a generator is closed when it is collected, or at `asyncio.run`'s shutdown if
something still holds it — a moment nothing controls, and its file or cursor stays open until then.
`aclosing` needs `aclose()`, so a method whose result callers close returns `AsyncGenerator`, not
`AsyncIterator` — mypy rejects the latter.

**Example:**
```python
# WRONG — returning mid-loop leaves the generator open; its finally waits for the collector
async def find_first_clear_scene(*, archive: SceneArchive) -> Scene | None:
    async for scene in archive.stream_scenes():
        if scene.is_cloud_free:
            return scene
    return None


# CORRECT — aclosing closes the generator on the way out, so its cursor is released here
async def find_first_clear_scene(*, archive: SceneArchive) -> Scene | None:
    async with aclosing(archive.stream_scenes()) as scenes:
        async for scene in scenes:
            if scene.is_cloud_free:
                return scene
    return None
```

## Context and Locks

### Per-task context travels in `contextvars`, and an `asyncio.Lock` guards state, never I/O

**Why:** a module global or a thread-local is shared by every task on the loop, so one capture's id
lands in another's log lines; a context variable is per task. It carries cross-cutting context —
a correlation id, a tenant — never business parameters smuggled past the signature. A lock held
across an external `await` you do not control makes every task that needs it wait for the network.

**Example:**
```python
# WRONG — one global for the whole loop: concurrent captures overwrite each other's id
_current_capture_id = ""


async def process_capture(capture: Capture, *, pipeline: CapturePipeline) -> None:
    global _current_capture_id  # noqa: PLW0603  # the bug this example shows
    _current_capture_id = capture.capture_id
    await pipeline.run(capture)


# CORRECT — each task sees the value set in its own context
_CAPTURE_ID: Final = contextvars.ContextVar[str]("capture_id", default="")


async def process_capture(capture: Capture, *, pipeline: CapturePipeline) -> None:
    _CAPTURE_ID.set(capture.capture_id)
    await pipeline.run(capture)
```

## Threads and the Loop

**Before handing work from a coroutine to a thread or a process pool, sharing state between threads
and tasks, or calling into the loop from a thread, read [threads.md](threads.md)** — `contextvars`
through `run_in_executor`, `call_soon_threadsafe`, `asyncio.Lock` against `threading.Lock`.

- Work submitted to an executor carries the caller's context explicitly
- A thread reaches the loop only through `run_coroutine_threadsafe` or `call_soon_threadsafe`
- `asyncio.Lock` only orders tasks; state a thread also touches takes a `threading.Lock`

## Shutdown

**Before handling `SIGTERM` or `SIGINT` or writing the stop path of a service, read
[shutdown.md](shutdown.md)** — a signal that sets an event, drain with a deadline, signals in the
main thread only.

- A signal sets an event; the application stops taking work, drains with a deadline, and closes
