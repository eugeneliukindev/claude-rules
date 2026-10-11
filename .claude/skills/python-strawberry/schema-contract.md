# The Schema as a Contract

### The SDL is exported, checked in, and compared in CI

**Why:** every schema change becomes a diff a reviewer reads in GraphQL, not in Python.
`strawberry export-schema` takes a schema or a zero-argument callable; CI exports again and fails on
any difference from the committed file.

**Example:**
```bash
# WRONG — the schema exists only as Python; a renamed field is a Python diff nobody reads as GraphQL
uv run pytest

# CORRECT — exported, and CI fails when the committed SDL no longer matches
uv run strawberry export-schema claims.graphql.schema:published_schema --output schema.graphql
git diff --exit-code schema.graphql
```

### A breaking change is found by graphql-core, not by eye

**Why:** `find_breaking_changes` compares the base branch's SDL with the branch's schema — a removed
field, a changed type, a new required argument — which a reviewer reading the diff misses when it is
one line among many.

**Example:**
```python
# WRONG — the diff is read, and a nullable field made non-null slips through
def has_schema_diff(base_branch_sdl: str) -> bool:
    return base_branch_sdl != published_schema().as_str()


# CORRECT — every change that breaks an existing client, listed
def breaking_schema_changes(base_branch_sdl: str) -> list[graphql.BreakingChange]:
    published = graphql.build_schema(base_branch_sdl)
    current = graphql.build_schema(published_schema().as_str())
    return graphql.find_breaking_changes(published, current)
```

### A field is deprecated before it is removed, and removed once its traffic has stopped

**Why:** `deprecation_reason` marks the field in the SDL and in every client's tooling. It goes once
the traffic on it has stopped — counted, not assumed (`python-observability`).

**Example:**
```python
# WRONG — the field simply removed: every client still asking for amount fails at once
@strawberry.type(name="Claim")
class ClaimObject:
    id: UUID
    claimed_amount: Decimal


# CORRECT — deprecated beside its replacement, until nobody asks for it
@strawberry.type(name="Claim")
class ClaimObject:
    id: UUID
    claimed_amount: Decimal
    amount: Decimal = strawberry.field(deprecation_reason="Use claimedAmount")
```
