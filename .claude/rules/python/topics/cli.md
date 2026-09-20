# Command-Line Interfaces

Not loaded automatically — open it when writing an entry point with an argument parser.

- **Never hand-parse arguments.** Use an argument parser whose declarations *are* the interface.
- **`main()` builds, `run()` executes**: the entry point constructs settings and the object graph,
  then calls a function that contains no construction.
- **Exit codes are the contract**: success, generic failure, usage error; further codes are named
  constants. Exit is called once, in `main()`, with the code returned by `run()` — never scattered
  through the code, never inside library functions.
- **stdout is the product, stderr is the conversation**: results go to stdout so they can be piped;
  logs, progress and errors go to stderr.
- **A dry-run mode for every command with side effects**; a verbosity flag mapped to log level; a
  machine-readable output mode where a human might not be the reader.
- **Subcommands are verbs, options are nouns**; boolean options are paired flags, never positional
  booleans.
- **Configuration precedence is fixed and documented**: explicit flag, then environment, then
  config file, then default. The CLI does not invent a fifth source.
- **Interrupts are graceful**: caught in `main()` only, cleanup runs, and no traceback is printed
  for them.
- **Long-running commands report progress**, are resumable where the work is batched, and never
  buffer all output until the end.
- **CLIs are tested through `run()`.** The argument layer contains no logic worth testing on its
  own.

Keeping a CLI's own interface compatible is the same problem as keeping a package's: see
`packaging.md`.
