---
name: python-cli
description: >-
  Designs a command-line interface with argparse, click or typer: arguments, exit codes, stdout
  against stderr, dry-run, configuration precedence, interrupts, tests. Use when writing an entry
  point that takes arguments, a command or subcommand, a __main__ block, or a sys.exit call.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---


# Command-Line Interfaces

Whatever the parser — argparse, click or typer. Keeping a CLI's own interface compatible is the same
problem as keeping a package's (`python-packaging`).

## Structure

### `main()` builds and exits once; `run()` does the work and returns the exit code

**Why:** the entry point constructs settings and the object graph and calls a function that contains
no construction. Exit codes are a contract — success, generic failure, usage error, further codes as
named constants — and exit is called once, in `main()`, with the code `run()` returned; an exit
inside the work gives a test `SystemExit` instead of a code.

**Example:**
```python
# WRONG — exits from inside run(): a test calling it gets SystemExit instead of a code
def run(*, backups: BackupService, older_than: date) -> int:
    try:
        backups.prune(older_than=older_than)
    except StorageError:
        logger.exception("pruning backups failed")
        sys.exit(EXIT_FAILURE)
    return EXIT_SUCCESS


# CORRECT — run() returns the code, and main() is the one place that exits
def run(*, backups: BackupService, older_than: date) -> int:
    try:
        backups.prune(older_than=older_than)
    except StorageError:
        logger.exception("pruning backups failed")
        return EXIT_FAILURE
    return EXIT_SUCCESS
```

### With click or typer, the decorated command is `main()`, never the work

**Why:** the command receives the parsed options, builds, calls `run()` and turns the code into
`raise typer.Exit(code)` (click: `sys.exit`). `CliRunner` then tests the argument layer and `run()`
is tested directly; work inside the decorated function is reachable only as argv strings.

**Example:**
```python
# WRONG — the work is in the command: a test must spell it as argv and parse stdout back
@app.command()
def list_stale(days: int = _DEFAULT_STALE_DAYS) -> None:
    for backup_id in _load_stale(days):
        print(backup_id)


# CORRECT — the command builds and calls run(); its code becomes the exit status
@app.command()
def list_stale(days: int = _DEFAULT_STALE_DAYS) -> None:
    exit_code = run(_load_stale(days), out=sys.stdout)
    raise typer.Exit(exit_code)
```

## Output and Options

### stdout carries the product; logs and progress go to stderr

**Why:** results on stdout can be piped; progress on stdout is read by the next command as data —
`list-stale | xargs` treats "searching…" as an id. Logging writes to stderr.

### A boolean option is a pair of flags, never a positional `type=bool`

**Why:** `type=bool` converts the string, and the string `"false"` is non-empty, so it is `True`.
`argparse.BooleanOptionalAction` gives `--dry-run` and `--no-dry-run` with a stated default.

**Example:**
```python
# WRONG — the argument "false" is a non-empty string, so dry_run is True
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prune-backups")
    parser.add_argument("dry_run", type=bool)
    return parser


# CORRECT — paired flags, with the default stated
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prune-backups")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
    return parser
```

### Configuration precedence is flag, then environment, then file, then default

**Why:** the order is fixed and documented, and the CLI invents no fifth source. An environment
variable read after parsing overrides the flag the user just typed; read into the default, it
yields to the flag.

**Example:**
```python
# WRONG — read after parsing, the environment overrides the flag the user just typed
def timeout_seconds(argv: Sequence[str]) -> float:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=_DEFAULT_TIMEOUT_SECONDS)
    arguments = parser.parse_args(argv)
    return float(os.environ.get(_TIMEOUT_VARIABLE, arguments.timeout_seconds))


# CORRECT — the environment replaces only the default, so a flag still wins
def timeout_seconds(argv: Sequence[str]) -> float:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.environ.get(_TIMEOUT_VARIABLE, _DEFAULT_TIMEOUT_SECONDS)),
    )
    seconds: float = parser.parse_args(argv).timeout_seconds
    return seconds
```

## Testing

### A CLI is tested through `run()`, with fakes injected and stdout captured

**Why:** through `main()` the test builds the real repository and receives the code as `SystemExit`;
the argument layer holds no logic worth testing on its own.

**Example:**
```python
# WRONG — through main(): it builds the real repository, and the code arrives as SystemExit
def test_run_prints_one_stale_id_per_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["list-stale", "--older-than", "2026-01-31"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == EXIT_SUCCESS


# CORRECT — through run(), with a fake injected and stdout captured
def test_run_prints_one_stale_id_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    backups = InMemoryBackupRepository(stale_ids=[BackupId(7), BackupId(9)])

    exit_code = run(backups=backups, older_than=date(2026, 1, 31))

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out == "7\n9\n"
```

## Interrupts and Pipes

**Before writing `main()` for a command that runs long or whose output is piped, read
[interrupts-and-pipes.md](interrupts-and-pipes.md)** — Ctrl-C caught once with exit code 130, a
closed pipe treated as a reader that left.
