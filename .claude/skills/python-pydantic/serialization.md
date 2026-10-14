# Serialization

### JSON comes from `model_dump_json`, a dict of primitives from `model_dump(mode="json")`

**Why:** `model_dump()` keeps `datetime`, `UUID` and `Decimal` as objects, and `json.dumps` refuses
them; `model_dump_json()` serializes straight from the core schema, every field in its wire format,
without the intermediate dict. A model is never `model_dump()` splatted into another class's
constructor: the next field added to one side arrives on the other unchecked, or fails there.

**Example:**
```python
# WRONG — model_dump() keeps datetime and Decimal as objects, and json.dumps refuses them
def germination_report_body(report: GerminationReport) -> str:
    return json.dumps(report.model_dump())


# CORRECT — serialized straight from the core schema
def germination_report_body(report: GerminationReport) -> str:
    return report.model_dump_json()
```

### `exclude_none`, `exclude_unset` and `exclude_defaults` are contract decisions

**Why:** each changes what a consumer sees. `exclude_unset` is the one for a PATCH payload — exactly
the fields that were set, an explicit `null` included; `exclude_none` drops that `null`, so a PATCH
can never clear a field.
