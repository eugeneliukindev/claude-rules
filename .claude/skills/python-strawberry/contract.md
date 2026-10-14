# Inputs and the Published Schema

### An input is a `@strawberry.input` type converted by `to_domain()`

**Why:** GraphQL already refuses a value of the wrong type with an error the client sees — a
malformed `UUID` argument fails as a variable error. Ranges, lengths and formats are the
conversion's, raising the domain's errors, in one method instead of in each resolver that takes the
input. A pydantic model that already exists is reused through `to_pydantic()` instead.

**Example:**
```python
# CORRECT — the input type converts itself, once
@strawberry.input(name="SubmitClaimInput")
class SubmitClaimInput:
    policy_number: str
    amount: Decimal

    def to_domain(self) -> ClaimSubmission:
        if self.amount <= 0:
            raise InvalidClaimAmountError(self.amount)
        return ClaimSubmission(policy_number=PolicyNumber(self.policy_number), amount=self.amount)


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def submit_claim(self, info: GraphQLInfo, submission: SubmitClaimInput) -> ClaimObject:
        claim = await info.context.claims.submit_claim(
            info.context.caller, submission.to_domain()
        )
        return ClaimObject.from_domain(claim)
```

### A mutation a client retries carries an idempotency key, minted by the client once per operation

**Why:** a client that resends `submitClaim` after a timeout files the claim twice; with a key the
service recognises the second request and answers it with the first one's result. The key is a
required `UUID` field on the input, and the service, not the resolver, stores and matches it.

### The SDL is exported, checked in, and compared in CI

**Why:** every schema change becomes a diff a reviewer reads in GraphQL, not in Python.
`strawberry export-schema` takes a schema or a zero-argument callable; CI exports again and fails on
any difference from the committed file.

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
the traffic on it has stopped — counted per field by a metric, not assumed.
