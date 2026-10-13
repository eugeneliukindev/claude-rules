# Serialization

### JSON comes from `model_dump_json`, a dict of primitives from `model_dump(mode="json")`

**Why:** `model_dump()` keeps `datetime`, `UUID` and `Decimal` as objects, and `json.dumps` refuses
them; `model_dump_json()` serializes straight from the core schema, every field in its wire format,
without the intermediate dict. A mapper is never `model_dump()` splatted into another class —
`to_domain()` and `from_domain()` name each field (`python-boundaries`).

**Example:**
```python
# WRONG — model_dump() keeps datetime and Decimal as objects, and json.dumps refuses them
def loan_receipt_body(receipt: LoanReceipt) -> str:
    return json.dumps(receipt.model_dump())


# CORRECT — serialized straight from the core schema
def loan_receipt_body(receipt: LoanReceipt) -> str:
    return receipt.model_dump_json()
```

### `exclude_none`, `exclude_unset` and `exclude_defaults` are contract decisions

**Why:** each changes what a consumer sees. `exclude_unset` is the one for a PATCH payload — exactly
the fields that were set, an explicit `null` included; `exclude_none` drops that `null`, so a PATCH
can never clear a field.
