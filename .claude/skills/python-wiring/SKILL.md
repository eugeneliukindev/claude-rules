---
name: python-wiring
description: >-
  Designs construction and configuration: one composition root, scopes, resource lifetime, settings,
  constants. ALWAYS invoke this skill when a task writes an entry point, main() or an application
  factory, opens a pool, client or connection, reads environment variables or a settings field, or
  fixes an import that connects. Do not wire objects directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Wiring: Composition Root, Resource Lifetime

In an ASGI service the composition root is the application's lifespan. Collaborators arrive through the constructor (`principles.md`), plain values instead of the settings object (`functions.md`), nothing runs at import (`modules.md`), and a test hands in fakes instead of patching (`testing.md`).

## Composition Root

- **Build everything in plain code in the composition root: a worker's or CLI's entry point, or a service's application factory.** It is the one place that knows every concrete class; a function below it that opens its own resources is a second root no test can hand another.
- **Use a container only at hundreds of objects, and never hand it below the root.** Below the root it is a service locator, and the signature no longer lists what the class needs.
- **Allow construction outside the root only for module-level names that hold nothing until the root configures them (`modules.md`), and for the task-queue app tasks are decorated with, its pools built by the worker's startup hook.**
- **Choose an implementation from settings in the root, never in a class.** A constructor that picks between implementations from a flag is a hidden second root: it must know every implementation's settings, and a test has to set the flag to reach the fake.
- **Default a collaborator only to what production runs, and only when that default needs no setting.** Write `clock: Clock | None = None` then `clock or WallClock()`, and `is None` instead of `or` when a valid value can be falsy; a default that needs a setting wastes the setting whenever the collaborator is passed. A plain value, like a path or a limit, is no collaborator and is defaulted in the signature (`functions.md`).
- **Make scopes explicit: build application-scoped objects once, and request-scoped ones through a passed factory.** An object with per-request state built once is shared between requests, and a pooled resource built per request exhausts the pool.

## Resource Lifetime

- **Release in the root what the root acquires, and let everything below borrow.**
- **Enter a resource through its own context manager, never a wrapper around it.** A wrapper is one more name to learn, and copied between projects it becomes a house convention. Enter an object with only `close()` through `contextlib.closing`; give an acquire-and-release pair the library leaves to the caller a `@contextmanager` named for what it yields, releasing in `finally`; write a class with `__enter__` and `__exit__` only when the object has other methods besides.
- **Open a known set of resources in one `with` or `async with` statement, one item per resource.** The parenthesized form closes them in reverse order and shows what is open; keep `ExitStack` and `AsyncExitStack` for a count known only at runtime.
- **Enter every pool, and run an async root once under `asyncio.run`.** A pool created with a bare `await` and never entered is closed by nobody, and the server logs its connections as dropped; in a web service the framework's startup and shutdown hook is the root.
- **Close only what the class built.** A resource passed in belongs to whoever passed it, and closing it breaks every other user; a class that builds its own and never closes it leaks one per instance.
- **Never let cleanup raise over the block's own error.** `__exit__` propagates by default, and a failed release replaces the error the caller needed; catch the release failure narrowly and log it on its own.
- **Never mutate process-wide state in library or service code.** A `chdir`, an environment variable or logging configuration changes every other caller for its duration; keep it to tests and entry points.

## Constants

- **Keep a constant next to its single user, and a shared one in the module that owns the concept.** A global grab-bag of constants is a module everyone imports and nobody owns.

## Settings

- **Read configuration into typed settings, built once at the root and unpacked there into the fields each part needs.** Below the root nothing takes the settings object (`functions.md`); `os.environ` read across the code is a dependency nobody declared, and a cached accessor behind `@lru_cache` is a global by another name, changed in a test only through `cache_clear()` and the environment.
- **Keep the server's settings in a class apart from the application's, and let each entry point build the classes of the parts it runs.** One class makes a worker supply a port it never binds, and lets the application's fields grow server knobs.
- **Never branch behaviour on the deployment environment's name; make each difference a setting of its own.** A branch on the name runs for the first time in the environment it guards, and every new environment must be added to every branch; use the name only as metadata, like a trace resource attribute or a log field.
- **Validate configuration at startup, before serving.** A missing or malformed variable then stops the process with a clear message instead of failing the first request hours later.
- **Make a feature flag a typed field read once and injected, never queried deep in the call stack.**
- **Test the settings class alone, with `monkeypatch.setenv` and `delenv`.** A loader reads the environment even when it skips the `.env` file, so a variable left in the shell fills a field the test never set.
- **Never put a secret in code, in a default or in a log.** A placeholder default lets a deploy that forgot the variable run with it, and a plain `str` secret is printed by the first `repr` of the settings.

## Parameter Objects

- **Pass a cohesive group of values as one frozen object.** Ask three questions: does the callee use essentially every field, is the name a concept (`RetryPolicy`) rather than an origin (`Settings`, `Config`, `Env`), could a test build it in one line from literals? Three yeses make a value to pass; one no makes it the configuration root under a smaller name.
- **Type the options a dispatcher forwards with `**options: Unpack[...]` over a `TypedDict` naming every field.** A misspelt option is then rejected at the call site; a builder missing a required field still fails only at the first call, so prefer builders that share one signature.
