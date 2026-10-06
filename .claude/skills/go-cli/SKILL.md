---
name: go-cli
description: >-
  Go command-line programs: main as a two-line shell around run, flags declared on a FlagSet that
  run owns rather than the global flag set, exit codes as a contract with one os.Exit in main,
  stdout for the product and stderr for the conversation, subcommands, dry-run and verbosity
  flags, configuration precedence, interrupts through signal.NotifyContext, and testing a command
  through run with buffers. Use when writing or reviewing a Go main package, a flag or a FlagSet,
  a subcommand, an os.Exit call, or a cobra or urfave/cli command.
---

# Command-Line Programs

## `main` Builds Nothing, `run` Does Everything

```go
func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}
```

- **`run` takes the arguments, the streams and the context**, and returns the exit code. Nothing
  inside it reads `os.Args`, writes `os.Stdout` or calls `os.Exit`, so a test calls it like any
  function and inspects two buffers.
- **`os.Exit` is called once, in `main`**, and nowhere else — it skips every `defer`, so an exit
  from deep inside leaves files unflushed and temporary directories behind. `log.Fatal` is
  `os.Exit` in disguise and is banned for the same reason — except in an `Example` function, which
  is a `main` in miniature (`go-examples`).
- **`main` therefore holds no `defer`** — `os.Exit` would skip it, and `gocritic`'s
  `exitAfterDefer` reports one. Signal handling starts inside `run` (Interrupts, below).

## Flags Are the Interface

- **A `flag.FlagSet` built inside `run`**, never the package-level `flag.Parse()`: the global set is
  shared by every test in the binary, and a second parse in the same process panics on the
  redefined flags.
- **Flags bind to typed values**: `flags.Duration`, `flags.Int64`, `flags.TextVar` for any type implementing
  `encoding.TextUnmarshaler` — an enum, an address, a log level. The flag package then validates
  and prints the error; `run` receives values, not strings.
- **`ContinueOnError`, so parsing fails with a code**: `flag.ErrHelp` is exit 0 after the usage
  text, any other parse error exit 2 — the convention every Unix tool follows.
- **Every flag has a usage string that says the unit and the default's meaning**: `"how long to
  wait for the server, e.g. 30s"`.
- **Subcommands are a map from name to function** — `commandsByName[args[0]]` — each with its own
  `FlagSet`. A framework (`cobra`, `urfave/cli`) is worth its dependency when there are many
  subcommands, shell completion, or generated docs; its `RunE` then calls the same `run`-shaped
  functions, and the framework stays in `main`.

## Exit Codes Are a Contract

| Code | Meaning |
|---|---|
| 0 | success — including `-h` |
| 1 | the operation failed: an error from the work itself |
| 2 | the invocation was wrong: unknown flag, missing argument |
| 130 | interrupted by a signal — 128 + SIGINT |

Name them as constants in `main`, document any code beyond these in the usage text, and never
reuse one for two meanings — a script branching on the code cannot tell them apart.

## Two Streams

- **stdout is the product** — the data a pipe or a redirect captures. **stderr is the
  conversation** — progress, warnings, errors, prompts. A command whose errors go to stdout
  corrupts the file a script redirected it into.
- **Output for machines is opt-in and stable**: `-format=json` writes one JSON document or one per
  line, and its shape is versioned like any API. The human format may change freely.
- **Errors print once, at the top**: `run` writes `program: what failed: why` to stderr and returns
  the code. Every layer below returns the error; none prints it.
- **No colour, no spinner when stderr is not a terminal**, and none when `NO_COLOR` is set.

## Behaviour Flags

- **`-dry-run` for anything destructive**, and it goes through the same code path as the real run
  up to the point of the side effect — a separate dry-run branch tests nothing.
- **`-v` raises the log level of the `slog` handler** built in `run`; it does not add `if verbose`
  checks around log calls.
- **Configuration precedence is fixed**: flags over environment over config file over defaults,
  resolved once in `run` into one settings struct. Every source is named in the usage text.
- **A prompt is skipped when stdin is not a terminal**, and a `-yes` flag answers it for scripts;
  a command that hangs waiting for input in CI has failed without saying so.

## Interrupts

```go
ctx, stop := signal.NotifyContext(ctx, os.Interrupt, syscall.SIGTERM)
defer stop()
context.AfterFunc(ctx, stop) // the first signal restores default handling: a second one kills
```

These are `run`'s first lines. Everything that blocks takes `ctx`, so the program stops at the next
cancellation point, runs its `defer`s, and returns 130 when `ctx.Err()` is set. The cause
`NotifyContext` records is only a message naming the signal; a program whose exit code must tell
SIGINT from SIGTERM receives them on its own channel with `signal.Notify`.

## Testing

```go
func TestRunRejectsUnknownFormat(t *testing.T) {
	var stdout, stderr bytes.Buffer

	code := run(t.Context(), []string{"-format=yaml", "report.csv"}, strings.NewReader(""), &stdout, &stderr)

	if code != exitUsage {
		t.Errorf("run() = %d, want %d", code, exitUsage)
	}
	if !strings.Contains(stderr.String(), `invalid value "yaml"`) {
		t.Errorf("stderr = %q, want it to name the invalid format", stderr.String())
	}
	if stdout.Len() != 0 {
		t.Errorf("stdout = %q, want nothing on a usage error", stdout.String())
	}
}
```

A test of the command checks the code, stdout and stderr — the three things a caller sees — and
covers the help text, a usage error, a failure of the work, and the happy path.
