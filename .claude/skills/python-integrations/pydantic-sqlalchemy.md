# pydantic and SQLAlchemy

The seam between `python-pydantic` and `python-sqlalchemy`, linked from both skills.

### A model is never validated from an ORM row with `from_attributes`

**Why:** `from_attributes=True` reads the row attribute by attribute, so every relationship the
model names is loaded there: one left lazy runs a statement per row, and a `lazy="raise"` one
arrives as a `ValidationError` — "Error extracting attribute: InvalidRequestError" (*measured* on
pydantic 2.14 and SQLAlchemy 2.1) — reported as bad data, far from the query that forgot to load
it. The repository turns the row into a domain object, and the model is built from that, field by
field.

**Example:**
```python
# WRONG — validating the row loads its pickings here, one statement per estate, or fails as data
@final
class TeaEstateResponse(StrictPayload):
    model_config = ConfigDict(from_attributes=True)

    name: str
    pickings: tuple[TeaPickingResponse, ...]


def tea_estate_response(row: TeaEstateRow) -> TeaEstateResponse:
    return TeaEstateResponse.model_validate(row)


# CORRECT — the domain object, loaded by the repository, is what the model is built from
@final
class TeaEstateResponse(StrictPayload):
    name: str
    pickings: tuple[TeaPickingResponse, ...]

    @classmethod
    def from_domain(cls, estate: TeaEstate) -> Self:
        pickings = tuple(TeaPickingResponse.from_domain(picking) for picking in estate.pickings)
        return cls(name=estate.name, pickings=pickings)
```
