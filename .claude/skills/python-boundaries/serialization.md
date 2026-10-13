# Serialization

## Contents

- A serialized type round-trips, and a test says so
- `NaN` and `Infinity` refused where a payload arrives
- A queued or stored shape carries its version

What a payload may publish — every field named, never a serialized domain object — is in
`SKILL.md`; protobuf and gRPC are `python-grpc`.

### A serialized type round-trips, and a test says so

**Why:** `from_dict(to_dict(value)) == value` is the contract a consumer relies on; a field that
serializes as a string and parses back as something else — a `Decimal` through a float, an aware
datetime through a naive one — corrupts data without an error. Every serialized type gets the test.

**Example:**
```python
# WRONG — the amount goes out as a float and comes back with a different value
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Refund:
    refund_id: RefundId
    amount: Decimal

    def to_dict(self) -> dict[str, object]:
        return {"refund_id": str(self.refund_id), "amount": float(self.amount)}


# CORRECT — the exact form goes out, and a round-trip test holds it there
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Refund:
    refund_id: RefundId
    amount: Decimal

    def to_dict(self) -> dict[str, object]:
        return {"refund_id": str(self.refund_id), "amount": str(self.amount)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            refund_id=RefundId(UUID(str(payload["refund_id"]))),
            amount=Decimal(str(payload["amount"])),
        )


def test_refund_round_trips_through_dict() -> None:
    refund = Refund(refund_id=RefundId(UUID(int=7)), amount=Decimal("19.90"))

    restored = Refund.from_dict(refund.to_dict())

    assert restored == refund
```

### `NaN` and `Infinity` are refused where a payload arrives

**Why:** they are not JSON, yet `json.loads` turns them into floats, and a validator's `float` may
accept them even in strict mode until it is told to refuse them. One bad number then poisons every
sum it joins.

**Example:**
```python
# WRONG — json.loads returns nan and inf for constants no JSON document may contain
def parse_reading(body: bytes) -> object:
    return json.loads(body)


# CORRECT — a non-standard constant is a malformed payload, refused where it arrives
def _reject_constant(name: str) -> Never:
    raise MalformedPayloadError(f"{name} is not a JSON number")


def parse_reading(body: bytes) -> object:
    return json.loads(body, parse_constant=_reject_constant)
```

### A shape that is queued or stored carries its version

**Why:** once the shape changes, a consumer cannot tell an old message from a new one. Consumers of
stored and queued data tolerate unknown *added* fields and migrate an old version on read; a
request still rejects extras. A cache entry is the exception: its version is in its key, and an old
entry is fetched again from the source, never migrated (`python-caching`). Binary formats follow the
same rules — explicit schema, explicit version, adapters at the edge.
