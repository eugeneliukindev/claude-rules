# FastAPI With Strawberry

The schema, the context class and the loaders are `python-strawberry`.

### The GraphQL router's context getter is a dependency, and it is where authentication happens

**Why:** `GraphQLRouter` runs `context_getter` as a FastAPI dependency, once per request, so it can
`Depends` on the principal: a missing or invalid token is a 401 before any resolver runs, and no
resolver reads a header. The context is a `BaseContext` subclass — the router accepts that or a
dict, and raises `InvalidCustomContext` for anything else.

**Example:**
```python
# WRONG — no principal: each resolver authenticates on its own, and the next one may not
async def get_context(connection: HTTPConnection) -> TrackerContext:
    tasks: TaskService = connection.state.task_service
    return TrackerContext(principal=None, tasks=tasks)


# CORRECT — the principal is a dependency of the getter, verified before GraphQL runs
async def get_context(
    connection: HTTPConnection, principal: Annotated[Principal, Depends(require_principal)]
) -> TrackerContext:
    tasks: TaskService = connection.state.task_service
    return TrackerContext(principal=principal, tasks=tasks)


graphql_router = GraphQLRouter(schema, context_getter=get_context, graphql_ide=None)
```

### The getter takes `HTTPConnection`, not `Request`

**Why:** the same getter serves the WebSocket route, which has no `Request`; measured with
`request: Request`, every subscription failed with a `TypeError` while every HTTP test passed. A
dependency raising `HTTPException` refuses the WebSocket handshake with the same 401.

**Example:**
```python
# WRONG — HTTP works; the WebSocket route cannot supply a Request, and every subscription fails
async def get_context(
    request: Request, principal: Annotated[Principal, Depends(require_principal)]
) -> TrackerContext:
    tasks: TaskService = request.state.task_service
    return TrackerContext(principal=principal, tasks=tasks)


# CORRECT — HTTPConnection is what both the HTTP and the WebSocket routes have
async def get_context(
    connection: HTTPConnection, principal: Annotated[Principal, Depends(require_principal)]
) -> TrackerContext:
    tasks: TaskService = connection.state.task_service
    return TrackerContext(principal=principal, tasks=tasks)
```
