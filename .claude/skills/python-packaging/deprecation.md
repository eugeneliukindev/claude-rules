# Compatibility and Deprecation

## Contents

- What counts as breaking, and a keyword-only parameter that is not
- Deprecate, then remove: `@deprecated`, the package's warning class, `stacklevel`
- A rename is a deprecated alias of the new name
- A removed module leaves a tombstone

`__all__` is the contract: anything not in it may change freely, anything in it follows these
rules. Every exported name is a promise, so the surface stays as small as viable.

### A breaking change ships only in a major, and a new keyword-only parameter is not one

**Why:** semantic versioning — breaking is major, a new capability minor, a fix patch. Breaking
includes removing or renaming an exported name, tightening accepted types, loosening returned
types, changing a default, reordering positional parameters and raising a new exception type from
an existing flow; a library that began deep-copying fields by default reverted it in the next
patch. A keyword-only parameter with a default is added freely — another reason for `*` in
signatures — and returned objects grow fields, so callers never destructure them exhaustively.

**Example:**
```python
# WRONG — a minor release inserts a positional parameter: every geocode(q, "DE", 5) call breaks
def geocode(
    query: str, region: str | None, country: str | None, limit: int, *, geocoder: Geocoder
) -> list[Place]:
    return geocoder.search(query, region=region, country=country, limit=limit)


# CORRECT — the new option is keyword-only with a default; existing calls are untouched
def geocode(
    query: str,
    country: str | None,
    limit: int,
    *,
    geocoder: Geocoder,
    region: str | None = None,
) -> list[Place]:
    return geocoder.search(query, region=region, country=country, limit=limit)
```

### A name is deprecated with a warning, a checker mark, its replacement and its versions

**Why:** a surprise removal breaks users who had no notice. `@deprecated(message)` (PEP 702,
`warnings` from 3.13, `typing_extensions` before) makes the checker flag every use and warns at
runtime; the category is the package's own `DeprecationWarning` subclass, so callers can filter it
apart from everyone else's. The message names the replacement, the version it was deprecated in
and the removal version once scheduled; the old path works for at least one minor release and is
removed only in a major. Python shows a `DeprecationWarning` by default only when it points into
`__main__`, so it must point at the caller's line: a hand-written `warn` counts every frame between
the caller and itself in `stacklevel` — a library whose wrapper called a helper with `stacklevel=2`
pointed every warning at its own code — and `skip_file_prefixes=` (3.12) skips the package's frames
however many there are.

**Example:**
```python
# WRONG — a generic category, no versions, attributed to this line instead of the caller's
def geocode_address(query: str, *, geocoder: Geocoder) -> list[Place]:
    warnings.warn("geocode_address is deprecated", DeprecationWarning)
    return geocode(query, None, _DEFAULT_LIMIT, geocoder=geocoder)


# CORRECT — the checker flags each use, and the warning lands on the caller's line
class AtlasDeprecationWarning(DeprecationWarning):
    pass


@deprecated(
    "geocode_address is deprecated since 2.3 and is removed in 3.0; use geocode",
    category=AtlasDeprecationWarning,
)
def geocode_address(query: str, *, geocoder: Geocoder) -> list[Place]:
    return geocode(query, None, _DEFAULT_LIMIT, geocoder=geocoder)
```

### A renamed name lives on as a deprecated alias of the new one, never a copy

**Why:** a copy is a second implementation the next fix misses. The alias resolves to the new
object and warns on access, so the old spelling keeps working and says what to write instead.

**Example:**
```python
# WRONG — atlas/_places.py: Place is a second class with Locality's body, and they drift
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Place:
    name: str
    coordinates: Coordinates


# CORRECT — atlas/__init__.py: the old name is the new class, with a warning on access
def __getattr__(name: str) -> object:
    if name == "Place":
        warnings.warn(
            "atlas.Place is deprecated since 2.3 and is removed in 3.0; use atlas.Locality",
            AtlasDeprecationWarning,
            stacklevel=2,
        )
        return Locality
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### A removed module leaves a tombstone that names its replacement

**Why:** the bare `ModuleNotFoundError` tells the caller nothing about where the code went.

**Example:**
```python
# WRONG — atlas/geo.py deleted in 3.0: "No module named 'atlas.geo'"


# CORRECT — atlas/geo.py, the whole file, kept for the 3.x series
raise ImportError("atlas.geo was removed in 3.0; import geocode and Locality from atlas")
```
