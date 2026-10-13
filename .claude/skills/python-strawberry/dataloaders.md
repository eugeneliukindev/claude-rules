# DataLoaders

## Contents

- Every field that loads by key goes through the request's loader
- One result per key, in key order
- One statement per batch, bounded
- Built per request
- A loader over owned data carries the principal

A resolver on a nested field runs once per parent: `claims { policyholder }` over fifty claims is
fifty lookups. `python-persistence` treats that as an error, and in GraphQL the client chooses the
nesting.

### Every field that loads by key goes through the request's `DataLoader`

**Why:** a loader collects the keys requested in one tick and calls its `load_fn` once. Measured:
seven claims over three policyholders made one call with three keys.

**Example:**
```python
# WRONG — one repository call per claim in the list
@strawberry.type(name="Claim")
class ClaimObject:
    id: UUID
    policyholder_id: strawberry.Private[PolicyholderId]

    @strawberry.field
    async def policyholder(self, info: GraphQLInfo) -> PolicyholderObject | None:
        policyholder = await info.context.policyholders.find(self.policyholder_id)
        return None if policyholder is None else PolicyholderObject.from_domain(policyholder)


# CORRECT — the loader batches every policyholder_id requested in this tick into one call
@strawberry.type(name="Claim")
class ClaimObject:
    id: UUID
    policyholder_id: strawberry.Private[PolicyholderId]

    @strawberry.field
    async def policyholder(self, info: GraphQLInfo) -> PolicyholderObject | None:
        policyholder = await info.context.policyholder_loader.load(self.policyholder_id)
        return None if policyholder is None else PolicyholderObject.from_domain(policyholder)
```

### The `load_fn` returns one result per key, in key order

**Why:** it receives the batch's keys — distinct while the loader's cache is on, the default. A
missing key is `None` in its slot, or an exception instance, raised to that key's caller alone. A
list of another length fails the whole batch with `WrongNumberOfResultsReturned`, and one in the
order the query produced hands each caller another policyholder's row.

**Example:**
```python
# WRONG — the rows in whatever order the query returned, one short when a key is missing
async def _load_policyholders(
    policyholders: PolicyholderRepository, policyholder_ids: list[PolicyholderId]
) -> list[Policyholder | None]:
    found = await policyholders.find_many(policyholder_ids)
    return list(found.values())


# CORRECT — mapped back onto the keys, None where a key has no row
async def _load_policyholders(
    policyholders: PolicyholderRepository, policyholder_ids: list[PolicyholderId]
) -> list[Policyholder | None]:
    found = await policyholders.find_many(policyholder_ids)
    return [found.get(policyholder_id) for policyholder_id in policyholder_ids]
```

### A batch is one statement, and `max_batch_size` bounds it

**Why:** `find_many` is `= ANY($1)` with the list in asyncpg (`python-asyncpg`), `IN` in SQLAlchemy
(`python-sqlalchemy`). The loader's batch is unbounded by default: a page of five thousand claims
sends one list of five thousand keys.

### A loader is built per request, never in the lifespan

**Why:** its cache is an unbounded dict on the instance: shared, it serves one user's rows to the
next, grows without end, and never sees a change.

**Example:**
```python
# WRONG — one loader for the process: its cache outlives every request and every update
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
    async with managed_pool(settings.database_url) as pool:
        policyholders = PostgresPolicyholderRepository(pool)
        loader = DataLoader(load_fn=partial(_load_policyholders, policyholders))
        yield {"policyholder_loader": loader}


# CORRECT — the lifespan holds the repository; the context getter builds a loader per request
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
    async with managed_pool(settings.database_url) as pool:
        yield {"policyholder_repository": PostgresPolicyholderRepository(pool)}
```

### A loader over owned data calls a service method that takes the principal

**Why:** a resolver that loads claims by id through a loader over the repository has skipped the
service's ownership check (`python-auth`). The integration test that pins the statement count per
use case still applies (`python-persistence`).

**Example:**
```python
# WRONG — straight from the repository: any claim id in the query is answered
async def _load_claims(claims: ClaimRepository, claim_ids: list[ClaimId]) -> list[Claim | None]:
    found = await claims.find_many(claim_ids)
    return [found.get(claim_id) for claim_id in claim_ids]


# CORRECT — through the service, which returns only what the principal may see
async def _load_claims(
    claims: ClaimService, principal: Principal, claim_ids: list[ClaimId]
) -> list[Claim | None]:
    visible = await claims.find_visible(principal, claim_ids)
    return [visible.get(claim_id) for claim_id in claim_ids]
```
