---
paths:
  - "**/*.py"
---

# Python - Modules

## Module Layout

### Every module has the same order

**Why:** a reader always knows where to look: a one-line docstring, imports and `__all__`,
constants and type aliases, the logger, exceptions, contracts, then concrete classes, public
functions high-level first, private functions after them in call order, and a `__main__` guard that
only calls `main()`. What will not fit is a seam, so the module is split rather than reordered.

### Nothing runs at import beyond constants, the logger and its kin

**Why:** a network call, a file read or a settings object at import makes every import slow and
order-dependent, and a test cannot import the module without the environment it reads.

**Example:**
```python
# WRONG - importing the module reads the environment
_settings = Settings()


def main() -> None:
    run(timeout_seconds=_settings.timeout_seconds)


# CORRECT - main() is a function, and it builds the settings
def main() -> None:
    settings = Settings()
    run(timeout_seconds=settings.timeout_seconds)
```

## Encapsulation

### A name used only inside its module or class takes an underscore

**Why:** functions, methods, attributes, constants, type aliases and classes alike - without the
prefix a name reads as surface, and the first outside import makes it surface for good. Constants
and aliases are the ones missed: read quietly from a second module, they get two owners. A name a
test imports is used outside, and stays unprefixed.
**Except:** a script nobody imports, and a name a framework reaches through a decorator - a route,
a fixture.

**Example:**
```python
# WRONG - the width, the formatter and the store all read as this module's surface
NUMBER_WIDTH: Final = 6


def format_number(sequence: int, *, width: int = NUMBER_WIDTH) -> str:
    return f"TKT-{sequence:0{width}d}"


@final
class TicketNumbering:
    def __init__(self, *, sequences: SequenceStore) -> None:
        self.sequences = sequences

    def next_number(self) -> str:
        return format_number(self.sequences.increment("support_ticket"))


# CORRECT - only the class and its one method are used outside, and only they lack the prefix
_NUMBER_WIDTH: Final = 6


def _format_number(sequence: int, *, width: int = _NUMBER_WIDTH) -> str:
    return f"TKT-{sequence:0{width}d}"


@final
class TicketNumbering:
    def __init__(self, *, sequences: SequenceStore) -> None:
        self._sequences = sequences

    def next_number(self) -> str:
        return _format_number(self._sequences.increment("support_ticket"))
```

### A package's `__init__.py` re-exports only the main names its consumers use

**Why:** a facade that re-exported everything made a job needing one enum load a browser driver and
an ORM; what only some need, or what pulls a heavy library, stays in a public module
`package/topic.py`, and what only siblings use is an internal `_topic.py`, never reached into.
**Except:** an application package nobody outside imports needs no facade.

## Imports

### Every direct dependency is declared, and none is feature-detected

**Why:** a package imported only because another dependency pulls it in disappears when that one
drops it; `try: import x` turns a missing dependency into a code path nobody tested.
