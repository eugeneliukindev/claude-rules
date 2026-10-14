---
name: python-cli
description: >-
  Designs a command-line interface with argparse, click or typer: arguments, exit codes, stdout
  against stderr, configuration precedence, interrupts, pipes, tests. Use when writing an entry
  point that takes arguments, a command or subcommand, a __main__ block, or a sys.exit call. Not
  for a one-off script (python-scripts).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---


# Command-Line Interfaces

Whatever the parser — argparse, click or typer. Keeping a CLI's own interface compatible is the same
problem as keeping a package's (`python-packaging`).

## Structure

### `main()` builds and exits once; `run()` does the work and returns the exit code

**Why:** exit codes are a contract — success, generic failure, usage error, further codes as named
constants — and exit is called once, in `main()`, with the code `run()` returned; an exit inside
the work gives a test `SystemExit` instead of a code.

**Example:**
```python
# WRONG — exits from inside run(): a test calling it gets SystemExit instead of a code
def run(srt: TextIO, *, shift_ms: int, out: TextIO) -> int:
    try:
        cues = parse_srt(srt)
    except MalformedCueError as error:
        print(error, file=sys.stderr)
        sys.exit(EXIT_INVALID_INPUT)
    out.write(render_webvtt(cues, shift_ms=shift_ms))
    return EXIT_SUCCESS


# CORRECT — run() returns the code, and main() is the one place that exits
def run(srt: TextIO, *, shift_ms: int, out: TextIO) -> int:
    try:
        cues = parse_srt(srt)
    except MalformedCueError as error:
        print(error, file=sys.stderr)
        return EXIT_INVALID_INPUT
    out.write(render_webvtt(cues, shift_ms=shift_ms))
    return EXIT_SUCCESS
```

### With click or typer, the decorated command is `main()`, never the work

**Why:** the command receives the parsed options, opens what the work needs, calls `run()` and
turns the code into `raise typer.Exit(code)` (click: `sys.exit`). `CliRunner` then tests the
argument layer and `run()` is tested directly; work inside the decorated function is reachable only
as argv strings.

**Example:**
```python
# WRONG — the work is in the command: a test must spell it as argv and parse stdout back
@app.command()
def shift(source: Path, shift_ms: int = 0) -> None:
    with source.open(encoding="utf-8") as srt:
        sys.stdout.write(render_webvtt(parse_srt(srt), shift_ms=shift_ms))


# CORRECT — the command opens the file and calls run(); its code becomes the exit status
@app.command()
def shift(source: Path, shift_ms: int = 0) -> None:
    with source.open(encoding="utf-8") as srt:
        exit_code = run(srt, shift_ms=shift_ms, out=sys.stdout)
    raise typer.Exit(exit_code)
```

## Output and Options

### stdout carries the product; logs and progress go to stderr

**Why:** results on stdout can be piped; progress on stdout is read by the next command as data —
`subconv shift pilot.srt > pilot.vtt` writes "converting…" into the subtitle file. Logging writes
to stderr.

### A boolean option is a pair of flags, never a positional `type=bool`

**Why:** `type=bool` converts the string, and the string `"false"` is non-empty, so it is `True`.
`argparse.BooleanOptionalAction` gives `--strict` and `--no-strict` with a stated default.

**Example:**
```python
# WRONG — the argument "false" is a non-empty string, so strict is True
def build_shift_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subconv")
    parser.add_argument("strict", type=bool)
    return parser


# CORRECT — paired flags, with the default stated
def build_shift_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subconv")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=False)
    return parser
```

### Configuration precedence is flag, then environment, then file, then default

**Why:** the order is fixed and documented, and the CLI invents no fifth source. An environment
variable read after parsing overrides the flag the user just typed; read into the default, it
yields to the flag.

**Example:**
```python
# WRONG — read after parsing, the environment overrides the flag the user just typed
def source_encoding(argv: Sequence[str], *, environ: Mapping[str, str]) -> str:
    parser = argparse.ArgumentParser(prog="subconv")
    parser.add_argument("--encoding", default=_DEFAULT_ENCODING)
    arguments = parser.parse_args(argv)
    return environ.get(_ENCODING_VARIABLE, arguments.encoding)


# CORRECT — the environment replaces only the default, so a flag still wins
def source_encoding(argv: Sequence[str], *, environ: Mapping[str, str]) -> str:
    parser = argparse.ArgumentParser(prog="subconv")
    parser.add_argument("--encoding", default=environ.get(_ENCODING_VARIABLE, _DEFAULT_ENCODING))
    encoding: str = parser.parse_args(argv).encoding
    return encoding
```

## Testing

### A CLI is tested through `run()`, its input and output in memory

**Why:** through `main()` the test opens a real file and receives the code as `SystemExit`; the
argument layer holds no logic worth testing on its own.

**Example:**
```python
# WRONG — through main(): it needs a file on disk, and the code arrives as SystemExit
def test_run_writes_cues_shifted_by_the_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["subconv", "pilot.srt", "--shift-ms", "500"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == EXIT_SUCCESS


# CORRECT — through run(), the subtitle text passed in and the output read back
def test_run_writes_cues_shifted_by_the_offset() -> None:
    srt = io.StringIO("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    out = io.StringIO()

    exit_code = run(srt, shift_ms=500, out=out)

    assert exit_code == EXIT_SUCCESS
    assert "00:00:01.500 --> 00:00:02.500" in out.getvalue()
```

## Interrupts and Pipes

**Before writing `main()` for a command that runs long or whose output is piped, read
[interrupts-and-pipes.md](interrupts-and-pipes.md)** — Ctrl-C caught once with exit code 130, a
closed pipe treated as a reader that left.

- Ctrl-C is caught once, in `main()`, after cleanup, without a traceback
- A closed pipe is a reader that left, not an error
