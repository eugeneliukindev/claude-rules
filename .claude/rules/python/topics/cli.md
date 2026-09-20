# Command-Line Interfaces and Public APIs

Not loaded automatically — open it when writing an entry point with an argument parser, or when
changing something code you do not control imports.

## Command-Line Interfaces

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

## API Compatibility and Deprecation

Applies to anything code you do not control imports or calls.

- **`__all__` is the contract.** Anything not in it may change freely; anything in it follows the
  rules below. Keep the public surface as small as viable — every exported name is a promise.
- **Semantic versioning semantics**: breaking change → major; new capability → minor; fix → patch.
  "Breaking" includes removing or renaming an exported name, tightening accepted types, loosening
  returned types, changing defaults, reordering positional parameters, and raising a new exception
  type from an existing flow.
- **Deprecate, then remove — never surprise.** Emit a deprecation warning *and* mark the name so
  type checkers and IDEs surface it; state the replacement and the removal version in the message;
  keep the old path working for at least one minor release; remove only in a major.
- **Design for extension without breakage**: keyword-only parameters can be added freely — another
  reason for `*` in signatures. Returned objects grow fields, so callers must not destructure
  exhaustively.
- **Renames are re-exports first**: the old name lives on as a deprecated alias of the new one,
  never a copy.
