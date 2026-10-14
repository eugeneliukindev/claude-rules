# Unions

### A union of models is discriminated on a literal field

**Why:** without a discriminator pydantic tries every member in turn, and a bad payload reports a
failure per member; `Field(discriminator="kind")` dispatches once on the tag and the error names
only the member it chose. Each member carries `kind: Literal[...]`.

**Example:**
```python
# WRONG — every member is tried in turn, and a bad payload reports a failure per member
@final
class SowingGuide(StrictPayload):
    method: DirectSowing | Transplanting


# CORRECT — dispatched on kind, and the error names only the member it chose
@final
class SowingGuide(StrictPayload):
    method: Annotated[DirectSowing | Transplanting, Field(discriminator="kind")]
```
