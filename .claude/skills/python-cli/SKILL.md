---
name: python-cli
description: >-
  Python command-line interface design with argparse, click or typer: an argument parser whose
  declarations are the interface, main() building and run() executing, exit codes as a contract
  with one sys.exit in main(), stdout for the product and stderr for the conversation, dry-run and
  verbosity flags, fixed configuration precedence, graceful interrupts, and testing through run().
  Use when writing or reviewing a Python entry point, an argparse, click or typer command, a
  subcommand, a __main__ block, or a sys.exit call and its exit codes.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Command-Line Interfaces

- **Never hand-parse arguments.** Use an argument parser whose declarations *are* the interface.
- **`main()` builds, `run()` executes**: the entry point constructs settings and the object graph,
  then calls a function that contains no construction.
- **Exit codes are the contract**: success, generic failure, usage error; further codes are named
  constants. Exit is called once, in `main()`, with the code returned by `run()` — never scattered
  through the code, never inside library functions.

```python
# WRONG — exits from inside run(): a test calling it gets SystemExit instead of a code
def run(*, invoices: InvoiceService, due_before: date) -> int:
    try:
        invoices.send_reminders(due_before=due_before)
    except DeliveryError:
        logger.exception("sending reminders failed")
        sys.exit(EXIT_FAILURE)
    return EXIT_SUCCESS

# CORRECT — run() returns the code, and main() is the one place that exits
def run(*, invoices: InvoiceService, due_before: date) -> int:
    try:
        invoices.send_reminders(due_before=due_before)
    except DeliveryError:
        logger.exception("sending reminders failed")
        return EXIT_FAILURE
    return EXIT_SUCCESS
```

- **With click or typer the decorated command is `main()`**: it receives the parsed options, builds,
  calls `run()` and turns the returned code into `raise typer.Exit(code)` (click: `sys.exit`).
  `CliRunner` then tests the argument layer, and `run()` is still tested directly — the work never
  lives in the decorated function, where only argv strings can reach it.

```python
# WRONG — the work is in the command: a test must spell it as argv and parse stdout back
@app.command()
def list_overdue(days: int = 30) -> None:
    for invoice_id in _load_overdue(days):
        print(invoice_id)

# CORRECT — the command builds and calls run(); its code becomes the exit status
@app.command()
def list_overdue(days: int = 30) -> None:
    exit_code = run(_load_overdue(days), days=days, out=sys.stdout)
    raise typer.Exit(exit_code)
```

- **stdout is the product, stderr is the conversation**: results go to stdout so they can be piped;
  logs, progress and errors go to stderr.

```python
# WRONG — progress shares stdout with the product: `list-overdue | xargs` reads it as an id
def run(*, invoices: InvoiceRepository, due_before: date) -> int:
    print(f"searching invoices due before {due_before}")
    for invoice_id in invoices.find_overdue_ids(due_before=due_before):
        print(invoice_id)
    return EXIT_SUCCESS

# CORRECT — progress is a log record, and logging writes to stderr; stdout carries only the ids
def run(*, invoices: InvoiceRepository, due_before: date) -> int:
    logger.info("searching overdue invoices", extra={"due_before": due_before.isoformat()})
    for invoice_id in invoices.find_overdue_ids(due_before=due_before):
        print(invoice_id)
    return EXIT_SUCCESS
```

- **A dry-run mode for every command with side effects**; a verbosity flag mapped to log level; a
  machine-readable output mode where a human might not be the reader.
- **Subcommands are verbs, options are nouns**; boolean options are paired flags, never positional
  booleans.

```python
# WRONG — a positional bool: the argument "false" is a non-empty string, so dry_run is True
parser.add_argument("dry_run", type=bool)

# CORRECT — paired flags, --dry-run and --no-dry-run, with the default stated
parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
```

- **Configuration precedence is fixed and documented**: explicit flag, then environment, then
  config file, then default. The CLI does not invent a fifth source.

```python
# WRONG — read after parsing, the environment overrides the flag the user just typed
parser.add_argument("--timeout-seconds", type=float, default=_DEFAULT_TIMEOUT_SECONDS)
arguments = parser.parse_args()
timeout_seconds = float(os.environ.get(_TIMEOUT_VARIABLE, arguments.timeout_seconds))

# CORRECT — the environment replaces only the default, so a flag on the command line still wins
parser.add_argument(
    "--timeout-seconds",
    type=float,
    default=float(os.environ.get(_TIMEOUT_VARIABLE, _DEFAULT_TIMEOUT_SECONDS)),
)
arguments = parser.parse_args()
timeout_seconds: float = arguments.timeout_seconds
```

- **Interrupts are graceful**: caught in `main()` only, cleanup runs, and no traceback is printed
  for them.

```python
EXIT_INTERRUPTED: Final = 130  # 128 + SIGINT, what a shell reports for Ctrl-C

# WRONG — Ctrl-C prints a traceback from wherever the work happened to be
def main() -> None:
    arguments = _build_parser().parse_args()
    due_before: date = arguments.due_before
    with build_invoice_service() as invoices:
        exit_code = run(invoices=invoices, due_before=due_before)
    sys.exit(exit_code)

# CORRECT — caught once, here; the with block has already closed the service on the way out
def main() -> None:
    arguments = _build_parser().parse_args()
    due_before: date = arguments.due_before
    try:
        with build_invoice_service() as invoices:
            exit_code = run(invoices=invoices, due_before=due_before)
    except KeyboardInterrupt:
        exit_code = EXIT_INTERRUPTED
    sys.exit(exit_code)
```

- **A closed pipe is not an error.** `list-overdue | head` closes stdout early; the next write
  raises `BrokenPipeError`, and Python prints a traceback and a second "Exception ignored" at exit,
  status 120. `main()` points stdout at `/dev/null` and exits as if the reader had read everything.

```python
# WRONG — piped into head, the run ends in two tracebacks and status 120
def main() -> None:
    exit_code = run(out=sys.stdout)
    sys.exit(exit_code)

# CORRECT — the reader left; the rest of the output goes nowhere, and the exit is clean
def main() -> None:
    try:
        exit_code = run(out=sys.stdout)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        exit_code = EXIT_SUCCESS
    sys.exit(exit_code)
```

- **Long-running commands report progress**, are resumable where the work is batched, and never
  buffer all output until the end.
- **CLIs are tested through `run()`.** The argument layer contains no logic worth testing on its
  own.

```python
# WRONG — through main(): it builds the real repository, and the code arrives as SystemExit
def test_run_prints_one_overdue_id_per_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["list-overdue", "--due-before", "2026-01-31"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == EXIT_SUCCESS

# CORRECT — through run(), with a fake injected and stdout captured
def test_run_prints_one_overdue_id_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    invoices = InMemoryInvoiceRepository(overdue_ids=[InvoiceId(7), InvoiceId(9)])

    exit_code = run(invoices=invoices, due_before=date(2026, 1, 31))

    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out == "7\n9\n"
```

Keeping a CLI's own interface compatible is the same problem as keeping a package's: see
the `python-packaging` skill.
