# Compatibility, Deprecation and Stability Tiers

## Contents

- What counts as breaking, and a keyword-only parameter that is not
- Deprecate, then remove: `@deprecated`, the package's warning class, `stacklevel`
- A rename is a deprecated alias of the new name
- A removed module leaves a tombstone
- A stability tier is a package

`__all__` is the contract: anything not in it may change freely, anything in it follows these
rules, so the surface stays as small as viable.

## Breaking Changes

### A breaking change ships only in a major, and a new keyword-only parameter is not one

**Why:** breaking includes removing or renaming an exported name, tightening accepted types,
loosening returned types, changing a default, reordering positional parameters and raising a new
exception type from an existing flow; a library that began deep-copying fields by default reverted
it in the next patch. A keyword-only parameter with a default is added freely, and returned objects
grow fields, so callers never destructure them exhaustively.

**Example:**
```python
# WRONG — a minor release inserts a positional parameter: every mix(a, b, 0.25) call breaks
def mix(first: Colour, second: Colour, space: ColourSpace, ratio: float) -> Colour:
    return space.interpolate(first, second, ratio)


# CORRECT — the new option is keyword-only with a default; existing calls are untouched
def mix(
    first: Colour, second: Colour, ratio: float, *, space: ColourSpace = ColourSpace.OKLAB
) -> Colour:
    return space.interpolate(first, second, ratio)
```

## Deprecation

### A name is deprecated with a warning, a checker mark, its replacement and its versions

**Why:** a surprise removal breaks users who had no notice. `@deprecated(message)` (PEP 702,
`warnings` from 3.13, `typing_extensions` before) makes the checker flag every use and warns at
runtime; the category is the package's own `DeprecationWarning` subclass, so callers can filter it
apart from everyone else's. The message names the replacement, the version it was deprecated in
and the removal version once scheduled; the old path works for at least one minor release and goes
only in a major. Python shows a `DeprecationWarning` by default only when it points into
`__main__`, so it must point at the caller's line: a hand-written `warn` counts every frame between
the caller and itself in `stacklevel` — a library whose wrapper called a helper with `stacklevel=2`
pointed every warning at its own code — and `skip_file_prefixes=` (3.12) skips the package's frames
however many there are.

**Example:**
```python
# WRONG — a generic category, no versions, attributed to this line instead of the caller's
def blend(first: Colour, second: Colour) -> Colour:
    warnings.warn("blend is deprecated", DeprecationWarning)
    return mix(first, second, _EVEN_RATIO)


# CORRECT — the checker flags each use, and the warning lands on the caller's line
class HuesDeprecationWarning(DeprecationWarning):
    pass


@deprecated(
    "blend is deprecated since 2.3 and is removed in 3.0; use mix",
    category=HuesDeprecationWarning,
)
def blend(first: Colour, second: Colour) -> Colour:
    return mix(first, second, _EVEN_RATIO)
```

### A renamed name lives on as a deprecated alias of the new one, never a copy

**Why:** a copy is a second implementation the next fix misses. The alias resolves to the new
object and warns on access, so the old spelling keeps working and says what to write instead.

**Example:**
```python
# WRONG — hues/_palette.py: Swatch is a second class with Colour's body, and they drift
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Swatch:
    hex_code: str
    name: str


# CORRECT — hues/__init__.py: the old name is the new class, with a warning on access
def __getattr__(name: str) -> object:
    if name == "Swatch":
        warnings.warn(
            "hues.Swatch is deprecated since 2.3 and is removed in 3.0; use hues.Colour",
            HuesDeprecationWarning,
            stacklevel=2,
        )
        return Colour
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### A removed module leaves a tombstone that names its replacement

**Why:** the bare `ModuleNotFoundError` tells the caller nothing about where the code went.

## Stability Tiers

| path | what it promises |
|---|---|
| `hues/` | the public surface, under the rules above |
| `hues/experimental/` | may change or vanish in any release |
| `hues/deprecated/` | still works, is going away, and says so on use |
| `hues/v1/` | the previous major, shipped alongside for migration |
| `hues/_internal/` | nothing |

### A stability tier is a package, so the import line states the terms

**Why:** a promise in a changelog is read once; one in the import path is re-read at every call
site — `from hues.experimental.harmony import HarmonyRule` says what the caller depends on. The
tier's `__init__.py` states the contract in one line, as `pydantic/experimental/__init__.py` does,
and moving a file between tiers is the release event a reviewer sees.
**Except:** a tier nobody needs — an application has one surface, and a library usually needs
`_internal/` and nothing more until the first thing it regrets shipping.
