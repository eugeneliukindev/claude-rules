# Dict Shapes and Constraints

## `TypedDict`

### Dict-shaped data that stays a dict is a `TypedDict`, turned into a domain object where it enters

**Why:** a JSON payload you don't own, a `**kwargs` bundle, a driver row, a file read back — the
`TypedDict` names the keys so `entry["designation"]` stops being `Any`, at no runtime cost. A file
read back stays dicts: converting every row costs more than it returns when most of the file is
only counted or filtered. It has no validation, methods or `isinstance`, so it is never a domain
type. Keys are marked `NotRequired[...]` or `Required[...]`, not `total=False`; `ReadOnly[...]` for
keys consumers must not change; `Unpack[Options]` types a forwarded `**kwargs`.

**Example:**
```python
# WRONG — the keys exist only in the author's head, and the dict travels inward
def parse_catalogue_entry(raw: dict[str, Any]) -> dict[str, Any]:
    return {"designation": raw["name"], "magnitude": raw.get("v_magnitude")}


# CORRECT — the TypedDict describes the foreign JSON; a domain object travels inward
class CatalogueEntryPayload(TypedDict):
    name: str
    v_magnitude: NotRequired[float | None]
    discovered_at: str


def parse_catalogue_entry(raw: CatalogueEntryPayload) -> CatalogueStar:
    v_magnitude = raw.get("v_magnitude")
    return CatalogueStar(
        designation=raw["name"],
        # is not None, not truthiness: Vega's magnitude is zero
        apparent_magnitude=Magnitude(v_magnitude) if v_magnitude is not None else None,
        discovered_at=datetime.fromisoformat(raw["discovered_at"]),
    )
```

## `Annotated`

### A constraint the type cannot express is an `Annotated` alias, named once

**Why:** `Literal` narrows which values; `Annotated` attaches rules the static type has no room for
— bounds, a pattern, a dependency marker — read at runtime by whatever validates the boundary;
`annotated_types` spells the bounds every validator reads. The same bounds in five models are five
places to get one wrong. A bound restated in a service body means the boundary leaked: domain code
receives values that are already valid.

**Example:**
```python
# WRONG — one limit, written into every request model
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ImagingRequest:
    exposure_seconds: Annotated[float, Interval(gt=0, le=3600)] = 60.0


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class SpectroscopyRequest:
    exposure_seconds: Annotated[float, Interval(gt=0, le=3600)] = 600.0


# CORRECT — the constrained type is named once and travels with its name
type ExposureSeconds = Annotated[float, Interval(gt=0, le=3600)]


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ImagingRequest:
    exposure_seconds: ExposureSeconds = 60.0


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class SpectroscopyRequest:
    exposure_seconds: ExposureSeconds = 600.0
```
