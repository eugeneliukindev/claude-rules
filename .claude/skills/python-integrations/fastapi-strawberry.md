# FastAPI and strawberry

The seam between `python-fastapi` and `python-strawberry`, linked from both skills.

### The GraphQL router's context getter is a dependency, and it is where authentication happens

**Why:** `GraphQLRouter` runs `context_getter` as a FastAPI dependency, once per request, so it can
`Depends` on the bearer dependency: a missing or invalid token is a 401 before any resolver runs,
and no resolver reads a header. The getter only reads what the lifespan built and adds the ranger.

**Example:**
```python
# WRONG — no ranger: each resolver authenticates on its own, and the next one may not
async def reserve_context(connection: HTTPConnection) -> ReserveContext:
    sightings: SightingService = connection.state.sightings
    return ReserveContext(ranger=None, sightings=sightings)


# CORRECT — the ranger is a dependency of the getter, verified before GraphQL runs
async def reserve_context(
    connection: HTTPConnection, ranger: Annotated[Ranger, Depends(authenticate_ranger)]
) -> ReserveContext:
    sightings: SightingService = connection.state.sightings
    return ReserveContext(ranger=ranger, sightings=sightings)


reserve_graphql = GraphQLRouter(reserve_schema, context_getter=reserve_context, graphql_ide=None)
```

### The context is a plain `BaseContext` subclass, never a frozen dataclass

**Why:** the router accepts a `BaseContext` subclass or a dict and raises `InvalidCustomContext`
for anything else, then writes `request`, `response` and `background_tasks` onto the instance —
measured on strawberry 0.334, a frozen dataclass context failed every request with
`FrozenInstanceError`. A plain subclass calls `BaseContext.__init__`, which declares those three,
and the resolvers still read it through one `strawberry.Info` alias.

**Example:**
```python
# WRONG — the router assigns context.request, and every query fails before its resolver
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ReserveContext(BaseContext):
    ranger: Ranger
    sightings: SightingService


# CORRECT — typed fields, and the router's own attributes declared by BaseContext.__init__
@final
class ReserveContext(BaseContext):
    def __init__(self, *, ranger: Ranger, sightings: SightingService) -> None:
        super().__init__()
        self.ranger = ranger
        self.sightings = sightings


type ReserveInfo = strawberry.Info[ReserveContext, None]
```

### The getter takes `HTTPConnection`, not `Request`

**Why:** the same getter serves the WebSocket route, which has no `Request`; measured with
`request: Request`, every subscription failed with a `TypeError` while every HTTP test passed. A
dependency raising `HTTPException` refuses the WebSocket handshake with the same 401.

**Example:**
```python
# WRONG — HTTP works; the WebSocket route cannot supply a Request, and every subscription fails
async def reserve_context(
    request: Request, ranger: Annotated[Ranger, Depends(authenticate_ranger)]
) -> ReserveContext:
    sightings: SightingService = request.state.sightings
    return ReserveContext(ranger=ranger, sightings=sightings)


# CORRECT — HTTPConnection is what both the HTTP and the WebSocket routes have
async def reserve_context(
    connection: HTTPConnection, ranger: Annotated[Ranger, Depends(authenticate_ranger)]
) -> ReserveContext:
    sightings: SightingService = connection.state.sightings
    return ReserveContext(ranger=ranger, sightings=sightings)
```
