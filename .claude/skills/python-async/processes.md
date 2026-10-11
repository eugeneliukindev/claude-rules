# Threads or Processes

## Contents

- The model follows the workload
- Executors are shared, injected and sized
- A process pool gets small picklable arguments
- The `multiprocessing` start method is named

| Workload | Model |
|---|---|
| Many concurrent network / DB waits | async |
| A blocking library with no async API | threads |
| CPU-bound Python | processes |
| CPU-bound inside a C extension that releases the GIL | threads |
| CPU-bound Python on 3.14, measured against processes | `InterpreterPoolExecutor`, or threads on a free-threaded `3.14t` build — if every C extension supports it |

Parallelism is measured before it is assumed: pool startup and pickling are real costs.

### An executor is built once by the composition root, sized by a constant, and passed in

**Why:** a pool per call starts and tears down its workers every time and breaks every concurrency
limit; one pool shared by the process is sized once and closed on shutdown (`python-wiring`).

**Example:**
```python
# WRONG — worker processes are started and torn down for every report
async def render_report(report_id: ReportId) -> bytes:
    with ProcessPoolExecutor() as pool:
        return await asyncio.get_running_loop().run_in_executor(pool, _render, report_id)


# CORRECT — one pool, sized and built by the composition root, passed in
async def render_report(report_id: ReportId, *, pool: Executor) -> bytes:
    return await asyncio.get_running_loop().run_in_executor(pool, _render, report_id)
```

### A process pool receives small picklable arguments and runs a module-level function

**Why:** every argument and result is pickled across the process boundary, so a loaded object costs
its whole size twice, and a lambda or a nested function cannot be pickled at all. Ids and paths go
in; the worker loads what it needs.

**Example:**
```python
# WRONG — the whole loaded dataset is pickled into the worker, and a lambda cannot be pickled
async def summarize(dataset: Dataset, *, pool: Executor) -> Summary:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(pool, lambda: dataset.summarize())


# CORRECT — the path crosses the boundary; a module-level function loads and summarizes
def _summarize_file(path: Path) -> Summary:
    return Dataset.load(path).summarize()


async def summarize(path: Path, *, pool: Executor) -> Summary:
    return await asyncio.get_running_loop().run_in_executor(pool, _summarize_file, path)
```

### The `multiprocessing` start method is `spawn` or `forkserver`, named explicitly

**Why:** forking a process that already has threads or an event loop is undefined behaviour in
practice. Since 3.14 the Linux default is `forkserver` rather than `fork`, so code that silently
relied on inherited globals breaks on upgrade; naming the method makes that dependence visible.

**Example:**
```python
# WRONG — the platform and the Python version pick the start method
def build_render_pool(*, workers: int = _RENDER_WORKERS) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=workers)


# CORRECT — named once, so the workers start the same way on every platform and version
def build_render_pool(*, workers: int = _RENDER_WORKERS) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn")
    )
```
