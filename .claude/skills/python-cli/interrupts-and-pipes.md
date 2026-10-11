# Interrupts and Pipes

### Ctrl-C is caught once, in `main()`, after cleanup, without a traceback

**Why:** an uncaught `KeyboardInterrupt` prints a traceback from wherever the work happened to be.
Caught in `main()` around the `with` that owns the resources, cleanup has already run, and the exit
is 130 — 128 plus `SIGINT`, what a shell reports for Ctrl-C.

**Example:**
```python
# WRONG — Ctrl-C prints a traceback from wherever the work happened to be
def main() -> None:
    arguments = build_parser().parse_args()
    older_than: date = arguments.older_than
    with build_backup_service() as backups:
        exit_code = run(backups=backups, older_than=older_than)
    sys.exit(exit_code)


# CORRECT — caught once, here; the with block has already closed the service on the way out
EXIT_INTERRUPTED: Final = 130  # 128 + SIGINT, what a shell reports for Ctrl-C


def main() -> None:
    arguments = build_parser().parse_args()
    older_than: date = arguments.older_than
    try:
        with build_backup_service() as backups:
            exit_code = run(backups=backups, older_than=older_than)
    except KeyboardInterrupt:
        exit_code = EXIT_INTERRUPTED
    sys.exit(exit_code)
```

### A closed pipe is a reader that left, not an error

**Why:** `list-stale | head` closes stdout early; the next write raises `BrokenPipeError`, and
Python prints a traceback and a second "Exception ignored" at exit, status 120. `main()` points
stdout at `/dev/null` and exits as if the reader had read everything.

**Example:**
```python
# WRONG — piped into head, the run ends in two tracebacks and status 120
def main() -> None:
    exit_code = run_listing(out=sys.stdout)
    sys.exit(exit_code)


# CORRECT — the reader left; the rest of the output goes nowhere, and the exit is clean
def main() -> None:
    try:
        exit_code = run_listing(out=sys.stdout)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        exit_code = EXIT_SUCCESS
    sys.exit(exit_code)
```
