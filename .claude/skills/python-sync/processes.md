# Process Pools

Which workload needs processes is the table in `SKILL.md`; awaiting a pool from a coroutine is
`python-async`.

### A process pool receives small picklable arguments and runs a module-level function

**Why:** every argument and result is pickled across the process boundary, so a loaded object costs
its whole size twice, and a lambda or a nested function cannot be pickled at all. Ids and paths go
in; the worker loads what it needs.

**Example:**
```python
# WRONG — every loaded dataset is pickled into a worker, and a lambda cannot be pickled at all
def summarize_all(datasets: Sequence[Dataset], *, pool: Executor) -> list[Summary]:
    return list(pool.map(lambda dataset: dataset.summarize(), datasets))


# CORRECT — paths cross the boundary; a module-level function loads and summarizes
def _summarize_file(path: Path) -> Summary:
    return Dataset.load(path).summarize()


def summarize_all(paths: Sequence[Path], *, pool: Executor) -> list[Summary]:
    return list(pool.map(_summarize_file, paths))
```

### The `multiprocessing` start method is `spawn` or `forkserver`, named explicitly

**Why:** forking a process that already has threads or an event loop is undefined behaviour in
practice. Since 3.14 the Linux default is `forkserver` rather than `fork`, so code that silently
relied on inherited globals breaks on upgrade; naming the method makes that dependence visible.

### A file run as a script that starts a pool calls `main()` under `if __name__ == "__main__"`

**Why:** under `spawn` and `forkserver` every worker imports the main module, and a pool started at
import fails — measured on 3.14: `RuntimeError: An attempt has been made to start a new process
before the current process has finished its bootstrapping phase`. A console-script entry point is
imported, never run as `__main__`, and needs no guard.

### A `BrokenProcessPool` is not caught per task: the process exits and its supervisor restarts it

**Why:** a worker killed mid-task — the kernel's OOM killer, a crash in a C extension — breaks the
whole pool: measured, the running future raised `BrokenProcessPool`, and so did every `submit`
after it. A loop that records the failure and moves on fails every remaining item the same way.
