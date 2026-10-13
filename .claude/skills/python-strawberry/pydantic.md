# The pydantic Integration

## Contents

- For an existing input model; output built from the domain
- Validation in `to_pydantic()`
- PEP 695 aliases written out
- No `all_fields`

In 0.333 it is `strawberry.experimental.pydantic` — `type`, `input`, `interface`, `error_type` —
with no stable module beside it. The mypy plugin, `strawberry.ext.mypy_plugin`, hooks only these
decorators; without it `to_pydantic` and `from_pydantic` are `attr-defined` errors.

### It is for an input whose pydantic boundary model already exists; output is built from the domain

**Why:** an input shared with a REST route or a queue runs that model's validators through
`to_pydantic()`, so the constraints live once (`python-pydantic`). A response model reused as a
GraphQL type makes two contracts change together, and the decorator writes `_strawberry_type` onto
the pydantic class, so one model backs one GraphQL type.

**Example:**
```python
# WRONG — the REST response model is also the GraphQL type: one change moves both contracts
@strawberry.experimental.pydantic.type(model=ClaimResponse, name="Claim")
class ClaimObject:
    id: strawberry.auto
    amount: strawberry.auto


# CORRECT — the submission model the REST route already validates with, reused as the input
@strawberry.experimental.pydantic.input(model=ClaimSubmissionPayload, name="SubmitClaimInput")
class SubmitClaimInput:
    policy_number: strawberry.auto
    amount: Decimal
```

### Validation runs in `to_pydantic()`, so a resolver reads the converted model, never the input

**Why:** GraphQL only type-checks the arguments; a resolver reading `submission.amount` straight off
the input skips every constraint. `to_pydantic()`'s `ValidationError` is the client's error: answer
it as a union member or leave it unmasked, as this skill's errors section says; masked, it reaches
the client as "Unexpected error." and the log as a failure.

**Example:**
```python
# WRONG — a negative amount goes straight to the service; the model's validators never run
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def submit_claim(self, info: GraphQLInfo, submission: SubmitClaimInput) -> ClaimObject:
        unchecked = ClaimSubmission(
            policy_number=PolicyNumber(submission.policy_number), amount=submission.amount
        )
        claim = await info.context.claims.submit_claim(info.context.principal, unchecked)
        return ClaimObject.from_domain(claim)


# CORRECT — the model's validators run first, and the service gets what they passed
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def submit_claim(self, info: GraphQLInfo, submission: SubmitClaimInput) -> ClaimObject:
        validated = submission.to_pydantic()
        checked = ClaimSubmission(
            policy_number=PolicyNumber(validated.policy_number), amount=validated.amount
        )
        claim = await info.context.claims.submit_claim(info.context.principal, checked)
        return ClaimObject.from_domain(claim)
```

### A field annotated with a PEP 695 alias gets its GraphQL type written out

**Why:** `strawberry.auto` cannot resolve a named constrained type — the aliases `python-pydantic`
asks for — and schema construction fails with `Unexpected type`.

**Example:**
```python
# WRONG — ClaimAmount is a `type` alias: "Unexpected type" when the schema is built
@strawberry.experimental.pydantic.input(model=ClaimSubmissionPayload, name="SubmitClaimInput")
class SubmitClaimInput:
    policy_number: strawberry.auto
    amount: strawberry.auto


# CORRECT — the GraphQL type stated on that field; the model still validates it
@strawberry.experimental.pydantic.input(model=ClaimSubmissionPayload, name="SubmitClaimInput")
class SubmitClaimInput:
    policy_number: strawberry.auto
    amount: Decimal
```

### The GraphQL type lists each field it publishes; never `all_fields=True`

**Why:** the model is shared, and with `all_fields` a field added to it for another consumer becomes
part of the GraphQL schema too.
