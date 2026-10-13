# Mutations

### An input is a `@strawberry.input` type converted by `to_domain()`

**Why:** GraphQL already refuses a value of the wrong type with an error the client sees — a
malformed `UUID` argument fails as a variable error. Ranges, lengths and formats are the
conversion's, raising the domain's errors, in one method instead of in each resolver that takes the
input. A pydantic model that already exists is reused through `to_pydantic()` instead.

**Example:**
```python
# WRONG — scalars converted inline: the next mutation that takes a claim repeats the checks
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def submit_claim(
        self, info: GraphQLInfo, policy_number: str, amount: Decimal
    ) -> ClaimObject:
        if amount <= 0:
            raise InvalidClaimError("amount must be positive")
        submission = ClaimSubmission(policy_number=PolicyNumber(policy_number), amount=amount)
        claim = await info.context.claims.submit_claim(info.context.principal, submission)
        return ClaimObject.from_domain(claim)


# CORRECT — the input type converts itself, once
@strawberry.input(name="SubmitClaimInput")
class SubmitClaimInput:
    policy_number: str
    amount: Decimal

    def to_domain(self) -> ClaimSubmission:
        if self.amount <= 0:
            raise InvalidClaimError("amount must be positive")
        return ClaimSubmission(policy_number=PolicyNumber(self.policy_number), amount=self.amount)


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def submit_claim(self, info: GraphQLInfo, submission: SubmitClaimInput) -> ClaimObject:
        claim = await info.context.claims.submit_claim(
            info.context.principal, submission.to_domain()
        )
        return ClaimObject.from_domain(claim)
```

### A mutation a client retries carries an idempotency key, minted by the client once per operation

**Why:** a client that resends `submitClaim` after a timeout files the claim twice; with a key the
service recognises the second request and answers it with the first one's result
(`python-boundaries`).
