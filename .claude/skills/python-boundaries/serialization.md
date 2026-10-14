# Serialization

What a payload may publish — every field named, never a serialized domain object — is in
`SKILL.md`; protobuf and gRPC are `python-grpc`.

### A serialized type round-trips, and a test says so

**Why:** `from_wire(to_wire(value)) == value` is the contract a consumer relies on; a field that
serializes as a string and parses back as something else — a `Decimal` through a float, an aware
datetime through a naive one — corrupts data without an error. Every serialized type gets the test.

**Example:**
```python
# WRONG — the height goes out as a float and comes back with a different value
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class TideLevel:
    gauge_id: TideGaugeId
    height_metres: Decimal

    def to_wire(self) -> dict[str, object]:
        return {"gauge_id": str(self.gauge_id), "height_metres": float(self.height_metres)}


# CORRECT — the exact form goes out, and a round-trip test holds it there
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class TideLevel:
    gauge_id: TideGaugeId
    height_metres: Decimal

    def to_wire(self) -> dict[str, object]:
        return {"gauge_id": str(self.gauge_id), "height_metres": str(self.height_metres)}

    @classmethod
    def from_wire(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            gauge_id=TideGaugeId(UUID(str(payload["gauge_id"]))),
            height_metres=Decimal(str(payload["height_metres"])),
        )


def test_tide_level_round_trips_through_wire() -> None:
    level = TideLevel(gauge_id=TideGaugeId(UUID(int=7)), height_metres=Decimal("3.40"))

    restored = TideLevel.from_wire(level.to_wire())

    assert restored == level
```

### `NaN` and `Infinity` are refused where a payload arrives

**Why:** they are not JSON, yet `json.loads` turns them into floats, and a validator's `float` may
accept them even in strict mode until it is told to refuse them. One bad number then poisons every
sum it joins.

**Example:**
```python
# WRONG — json.loads returns nan and inf for constants no JSON document may contain
def parse_gauge_report(body: bytes) -> object:
    return json.loads(body)


# CORRECT — a non-standard constant is a malformed payload, refused where it arrives
def _reject_constant(name: str) -> Never:
    raise MalformedGaugeReportError(f"{name} is not a JSON number")


def parse_gauge_report(body: bytes) -> object:
    return json.loads(body, parse_constant=_reject_constant)
```

### A shape that is queued or stored carries its version

**Why:** once the shape changes, a consumer cannot tell an old message from a new one. Consumers of
stored and queued data tolerate unknown *added* fields and migrate an old version on read; a
request still rejects extras. Binary formats follow the same rules — explicit schema, explicit
version, adapters at the edge.
**Except:** a cache entry carries its version in its key, and an old entry is fetched again from the
source, never migrated.
