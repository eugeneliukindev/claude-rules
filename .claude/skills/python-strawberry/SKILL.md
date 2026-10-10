---
name: python-strawberry
description: >-
  strawberry-graphql practice, with strawberry.fastapi.GraphQLRouter and the experimental pydantic
  integration: strawberry types as the wire layer built from domain objects, a typed context from
  context_getter over what the lifespan built, a DataLoader per request against N+1, depth, token
  and alias limits passed as factories, introspection, GraphiQL and field suggestions turned off,
  bounded list fields, domain errors as union results through exception_handlers, MaskErrors and
  error logging done once, permission classes as a coarse gate, sync resolvers that block the
  event loop, subscriptions, testing with schema.execute and through the app, and the exported SDL
  checked for breaking changes. Use when Python code imports strawberry, defines a strawberry.type,
  a resolver, a DataLoader, a GraphQLRouter or a schema extension, or serves or tests GraphQL.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Strawberry GraphQL

Checked against strawberry-graphql 0.332, graphql-core 3.3, FastAPI 0.143, Starlette 1.7 and
pydantic 2.14, by reading the installed source and running every `CORRECT` below. Strawberry is
0.x and renames and deprecates between minor versions — check the source of the version you pin.
The factory, the lifespan and `Depends` are `python-fastapi`; construction and lifetime
`python-wiring`. This file is where strawberry's mechanisms meet those rules.

**Typing.** Under `mypy --strict`, a decorator called with arguments —
`@strawberry.field(description=...)`, `@strawberry.mutation(extensions=[...])` — is reported as
`untyped-decorator`: those overloads return `Any`. The bare `@strawberry.field` is typed. Nothing
calls a resolver by its attribute, so the GraphQL package takes one named override instead of an
ignore on every resolver:

```toml
[[tool.mypy.overrides]]
module = ["shop.graphql.*"]
disallow_untyped_decorators = false  # strawberry types field(...) and mutation(...) as Any
```

The mypy plugin, `strawberry.ext.mypy_plugin`, hooks only the `experimental.pydantic`
decorators; without it `to_pydantic` and `from_pydantic` are `attr-defined` errors. **A union is a
plain assignment**, the one alias that is not a `type` statement: `type RefundOrderResult =
Annotated[..., strawberry.union(...)]` fails schema construction with `Unexpected type`.

## Strawberry Types Are the Wire Layer

A `@strawberry.type` is a response model (`python-boundaries`): built from the domain object, never
the domain object decorated. The schema publishes every field of the class it is given, so a
decorated domain class publishes the next field anyone adds to it, and the domain imports the
transport (`python-layers`).

```python
# WRONG — the domain class is the wire type: owner_id is published, and so is every later field
@strawberry.type
class Order:
    order_id: OrderId
    owner_id: UserId
    total: Decimal


# CORRECT — the wire type names what it publishes and is built from the domain Order
@strawberry.type(name="Order")
class OrderObject:
    id: UUID
    total: Decimal
    customer_id: strawberry.Private[CustomerId]

    @staticmethod
    def from_domain(order: Order) -> "OrderObject":
        return OrderObject(id=order.order_id, total=order.total, customer_id=order.customer_id)
```

- **`name=` pins the published name.** The schema takes type names from Python class names and
  field names from attributes, camel-cased; without the pin, renaming a Python class renames a
  type every client queries. The Python name carries the family suffix, the schema the domain word.
- **`strawberry.Private[...]` is a field the resolvers read and the schema never shows** — here the
  key the customer loader needs.
- **A resolver translates and calls one service method**, as a FastAPI route does
  (`python-fastapi`); a rule in a resolver is reachable only through GraphQL.

### The pydantic Integration Is Still `experimental`

In 0.332 it is `strawberry.experimental.pydantic` — `type`, `input`, `interface`, `error_type` —
with no stable module beside it. It earns its place for **an input whose pydantic boundary model
already exists**, shared with a REST route or a queue: `to_pydantic()` runs that model's validators,
so the constraints live once (`python-pydantic`). For output, build strawberry types from the
domain as above: a response model reused as a GraphQL type makes two contracts change together.

- **Validation runs in `to_pydantic()` and nowhere else.** The arguments are only type-checked
  by GraphQL; a resolver reading `order.quantity` straight off the input skips every constraint.
- **Its `ValidationError` is the client's error.** Answer it as a union member or leave it
  unmasked (below); masked, it reaches the client as "Unexpected error." and the log as a failure.
- **`strawberry.auto` cannot resolve a field annotated with a PEP 695 alias** — the named
  constrained types `python-pydantic` asks for. Schema construction fails with `Unexpected type`;
  write the GraphQL type on that field (`quantity: int`).
- **The decorator writes `_strawberry_type` onto the pydantic class**, so one model backs one
  GraphQL type.

```python
# WRONG — all_fields: a field added to the model for another consumer is published here too
@strawberry.experimental.pydantic.type(model=CustomerPayload, all_fields=True)
class CustomerObject:
    pass


# CORRECT — the GraphQL type lists each field it publishes
@strawberry.experimental.pydantic.type(model=CustomerPayload)
class CustomerObject:
    name: strawberry.auto
    email: strawberry.auto
```

## The Context Is Built From What the Lifespan Built

`context_getter` is a FastAPI dependency — it can `Depends` on others — and runs once per request.
It reads the services the lifespan put on the connection's state and builds only what is
request-scoped: the principal, the loaders. A pool or a client built here is built per request,
and a module-level service is the global `python-wiring` forbids.

- **The context is a `BaseContext` subclass.** The router accepts that or a dict, and raises
  `InvalidCustomContext` for anything else; a dict is `dict[str, Any]` in every resolver.
  Resolvers take one alias, `GraphQLInfo`, and see a typed `info.context`.
- **Authentication happens here, once** — the principal is a dependency of the getter, and its
  failure is an HTTP 401 before any GraphQL runs. A GraphQL API is one route, so this is the
  protected router of `python-fastapi`; how the token is verified is `python-auth`.

```python
@final
class GraphQLContext(BaseContext):
    def __init__(
        self,
        *,
        principal: Principal,
        orders: OrderService,
        customer_loader: DataLoader[CustomerId, Customer | None],
    ) -> None:
        super().__init__()
        self.principal = principal
        self.orders = orders
        self.customer_loader = customer_loader


type GraphQLInfo = strawberry.Info[GraphQLContext, None]


async def get_context(
    connection: HTTPConnection, principal: Annotated[Principal, Depends(require_principal)]
) -> GraphQLContext:
    orders: OrderService = connection.state.order_service
    customers: CustomerRepository = connection.state.customer_repository
    return GraphQLContext(
        principal=principal,
        orders=orders,
        customer_loader=DataLoader(load_fn=partial(_load_customers, customers)),
    )
```

- **The getter takes `HTTPConnection`, not `Request`.** The same getter serves the WebSocket
  route; measured with `request: Request`, every subscription failed with a `TypeError` while every
  HTTP test passed. A dependency raising `HTTPException` refuses the WebSocket handshake with the
  same 401.

```python
# WRONG — HTTP works; the WebSocket route cannot supply a Request, and every subscription fails
async def get_context(request: Request, principal: PrincipalDep) -> GraphQLContext: ...

# CORRECT — HTTPConnection is what both the HTTP and the WebSocket routes have
async def get_context(connection: HTTPConnection, principal: PrincipalDep) -> GraphQLContext: ...
```

## N+1 Is an Error: One DataLoader per Request

A resolver on a nested field runs once per parent: `orders { customer }` over fifty orders is
fifty customer lookups. `python-persistence` treats that as an error; in GraphQL the client chooses
the nesting, so every field that loads by key goes through a `DataLoader`, which collects the keys
requested in one tick and calls its `load_fn` once.

```python
# WRONG — one repository call per order in the list
@strawberry.field
async def customer(self, info: GraphQLInfo) -> CustomerObject | None:
    customer = await info.context.customers.find(self.customer_id)
    return None if customer is None else CustomerObject.from_domain(customer)


# CORRECT — the loader batches every customer_id requested in this tick into one call
@strawberry.field
async def customer(self, info: GraphQLInfo) -> CustomerObject | None:
    customer = await info.context.customer_loader.load(self.customer_id)
    return None if customer is None else CustomerObject.from_domain(customer)
```

- **The `load_fn` returns one result per key, in key order.** It receives the batch's keys —
  distinct while the loader's cache is on, the default. A missing key is `None` in its slot, or
  an exception instance, raised to that key's caller alone. A list of another length fails the
  whole batch with `WrongNumberOfResultsReturned`, so the rows are mapped back onto the keys —
  never returned in whatever order the query produced them.
- **One statement per batch**: `= ANY($1)` with the list in asyncpg (`python-asyncpg`), `IN` in
  SQLAlchemy (`python-sqlalchemy`); `max_batch_size=` bounds the list. Measured: seven orders over
  three customers made one call with three keys.

```python
async def _load_customers(
    customers: CustomerRepository, customer_ids: list[CustomerId]
) -> list[Customer | None]:
    found = await customers.find_many(customer_ids)
    return [found.get(customer_id) for customer_id in customer_ids]
```

- **A loader is built per request, never in the lifespan.** Its cache is an unbounded dict on the
  instance: shared, it serves one user's rows to the next and never sees a change.
- **A loader over owned data does not bypass authorization.** A resolver that loads orders by id
  through a loader has skipped the service's ownership check; its `load_fn` calls a service
  method that takes the context's principal (`python-auth`). The integration test that pins the
  statement count per use case still applies (`python-persistence`).

## A Query Has a Cost Limit

A client writes the query, so the server bounds it before running it: depth, size, aliases and the
length of every list. All are schema extensions, and **extensions are passed as classes or
factories** — in 0.332 an instance in `extensions=[...]` raises a `DeprecationWarning`, which
`filterwarnings = ["error"]` turns into a failing suite, and `mypy` already rejects. A list built
apart from the call is annotated — unannotated, a class beside a `partial` is `list[object]`.

```python
# WRONG — instances: deprecated, and one object is shared by every request
extensions: list[Callable[[], SchemaExtension]] = [
    QueryDepthLimiter(max_depth=_MAX_QUERY_DEPTH),
    DisableIntrospection(),
]

# CORRECT — a class or a factory: a fresh extension for every operation
extensions: list[Callable[[], SchemaExtension]] = [
    partial(QueryDepthLimiter, max_depth=_MAX_QUERY_DEPTH),
    DisableIntrospection,
]
```

```python
def build_schema(*, is_introspection_enabled: bool) -> strawberry.Schema:
    extensions: list[Callable[[], SchemaExtension]] = [
        partial(QueryDepthLimiter, max_depth=_MAX_QUERY_DEPTH),
        partial(MaxTokensLimiter, max_token_count=_MAX_QUERY_TOKENS),
        partial(MaxAliasesLimiter, max_alias_count=_MAX_ALIASES),
        partial(MaskErrors, should_mask_error=_is_unexpected),
    ]
    if not is_introspection_enabled:
        extensions.append(DisableIntrospection)
    return _ServerErrorLoggingSchema(
        query=Query,
        mutation=Mutation,
        extensions=extensions,
        exception_handlers=[_OrderNotFoundHandler()],
        config=StrawberryConfig(disable_field_suggestions=not is_introspection_enabled),
    )
```

- **`QueryDepthLimiter` counts through fragments** — measured — **but not breadth.** Depth five
  with a hundred items per level is ten billion objects; the depth limit cannot see a list.
- **Every list field is bounded**: a `first` argument with a ceiling the resolver enforces —
  raising `GraphQLError`, which the client sees — and a keyset cursor for the next page
  (`python-persistence`). A list with no argument returns whatever the table holds.
- **Where the schema is private, all three discovery paths close together**:
  `DisableIntrospection`, `graphql_ide=None` on the router — GraphiQL is on by default — and
  `disable_field_suggestions=True`. Without the last, a typo is answered with
  `Did you mean 'refundOrder'?`, and the field names come out one guess at a time.
- **Batching is off by default.** Enabled with `batching_config={"max_operations": n}`, every
  operation in the batch pays the limits on its own, so `n` multiplies them.
- **No persisted-query or operation-allowlist extension ships in 0.332.** An allowlist is a
  `SchemaExtension` of your own or the gateway's job.
- **GET runs queries and refuses mutations** (400) by default; `allow_queries_via_get=False`
  where nothing caches GET responses.

## Errors: Classified Ones Are Results, the Rest Are Masked and Logged Once

GraphQL answers 200 with an `errors` list; the HTTP status says only that the request was
understood. What `python-fastapi` does with one exception handler — a classified domain error
becomes a stated answer, anything else a fixed message — strawberry does with two mechanisms.

**A classified domain error is a member of the field's result union.** `exception_handlers=` on the
schema converts an exception into an error type, on every field whose return union contains that
type — the mapping is in one place and the service raises its own errors. Subscriptions are
excluded.

```python
@strawberry.type
class OrderNotFound:
    order_id: UUID
    message: str


RefundOrderResult = Annotated[OrderObject | OrderNotFound, strawberry.union("RefundOrderResult")]


@final
class _OrderNotFoundHandler(strawberry.ExceptionHandler[OrderNotFoundError, OrderNotFound]):
    @override
    def handle(
        self, exception: OrderNotFoundError, *, field: StrawberryField, info: strawberry.Info
    ) -> OrderNotFound:
        return OrderNotFound(order_id=exception.order_id, message=str(exception))


@strawberry.type
class Mutation:
    @strawberry.mutation(extensions=[PermissionExtension(permissions=[HasScope(_REFUND_SCOPE)])])
    async def refund_order(self, info: GraphQLInfo, order_id: UUID) -> RefundOrderResult:
        order = await info.context.orders.refund_order(info.context.principal, OrderId(order_id))
        return OrderObject.from_domain(order)
```

**Everything else is masked — and only that.** `MaskErrors()` with its default masks every error:
measured, a syntax error, an unknown field and a depth violation all became "Unexpected error.",
and a client cannot fix a query it is not told is wrong. Mask what an unexpected exception raised;
validation errors, permission refusals and a `GraphQLError` a resolver raised on purpose stay as
they are.

```python
# WRONG — the default predicate masks everything, the client's own mistakes included
extensions: list[Callable[[], SchemaExtension]] = [MaskErrors]

# CORRECT — only an error caused by an exception nobody classified is masked
def _is_unexpected(error: GraphQLError) -> bool:
    return error.original_error is not None and not isinstance(error.original_error, GraphQLError)

extensions: list[Callable[[], SchemaExtension]] = [
    partial(MaskErrors, should_mask_error=_is_unexpected)
]
```

**Logging happens once, for the unexpected ones.** `Schema.process_errors` logs every error at
`ERROR` with its traceback on the `strawberry.execution` logger — a client's typo pages someone
(`logging.md`). Override it; it runs before `MaskErrors`, so it still sees the original exception.

```python
@final
class _ServerErrorLoggingSchema(strawberry.Schema):
    @override
    def process_errors(
        self, errors: list[GraphQLError], execution_context: ExecutionContext | None = None
    ) -> None:
        for error in errors:
            if _is_unexpected(error):
                logger.error(
                    "graphql resolver failed",
                    exc_info=error.original_error,
                    extra={"graphql_path": error.path},
                )
```

## Authorization: a Permission Class Gates, the Service Decides

- **A permission class is the coarse gate** — a scope, a role — checked before the resolver runs,
  with a fixed message whatever failed (`python-auth`). Attach it as
  `extensions=[PermissionExtension(...)]`; the source documents the older `permission_classes=`
  wrapping as deprecated.
- **Ownership is decided in the service**, which loads the object: the permission class has not
  seen the order. Above, someone else's order comes back as `OrderNotFound`, exactly like a
  missing one — the IDOR rule of `python-auth`, answered as a union member.

```python
@final
class HasScope(BasePermission):
    message = "Not allowed"

    def __init__(self, scope: str) -> None:
        self._scope = scope

    @override
    def has_permission(self, source: Any, info: strawberry.Info, **kwargs: Any) -> bool:
        context: GraphQLContext = info.context
        return self._scope in context.principal.scopes
```

`has_permission` keeps the library's `Any` parameters, and the annotated local states the context
type once, as `python-fastapi`'s accessors do. `PermissionExtension` publishes each class as a
directive in the SDL — `directive @hasScope on FIELD_DEFINITION` — so the schema names its
authorization rules; `use_directives=False` keeps them out.

## Mutations

- **Inputs are `@strawberry.input` types converted by `to_domain()`**, or a pydantic model through
  `to_pydantic()` (above). GraphQL already refuses a value of the wrong type with an error the
  client sees — a malformed `UUID` argument fails as a variable error; ranges, lengths and formats
  are the conversion's, raising the domain's errors.
- **A mutation a client retries carries an idempotency key** in its input, minted by the client
  once per operation (`python-boundaries`). Without one, a client that resends `placeOrder` after a
  timeout places the order twice.

## `def` Resolvers Run on the Event Loop

Unlike a FastAPI `def` route, a `def` resolver is not sent to a thread pool: strawberry calls it
inside the event loop. Measured: three concurrent queries of a `def` resolver sleeping 0.5 s took
1.5 s, all on the main thread. Anything that blocks is offloaded (`python-async`).

```python
# WRONG — the blocking client stops every other request on the worker while it waits
@strawberry.field
def invoice(self, info: GraphQLInfo, invoice_id: UUID) -> InvoiceObject:
    invoice = info.context.billing.fetch_invoice(InvoiceId(invoice_id))
    return InvoiceObject.from_domain(invoice)


# CORRECT — the blocking call runs on a worker thread and the loop keeps serving
@strawberry.field
async def invoice(self, info: GraphQLInfo, invoice_id: UUID) -> InvoiceObject:
    invoice = await asyncio.to_thread(info.context.billing.fetch_invoice, InvoiceId(invoice_id))
    return InvoiceObject.from_domain(invoice)
```

A `def` resolver that only computes from what it already holds blocks nothing and stays a `def`.

## Subscriptions

A subscription gets a bounded queue per subscriber, releases what it holds on disconnect, ends after
a maximum lifetime, fans out between workers through a channel contract, and checks `Origin` (why
and how: `python-streaming`). Strawberry's part:

- **A subscription is an async generator.** On the client's `complete` or a disconnect strawberry
  closes it, and its `finally` runs; a generator it iterates is closed with `aclosing`
  (`python-async`) — measured, both released.

```python
@strawberry.type
class Subscription:
    @strawberry.subscription
    async def order_status(
        self, info: GraphQLInfo, order_id: UUID
    ) -> AsyncGenerator[OrderStatusChanged]:
        events = follow_order(
            info.context.order_feed, OrderId(order_id), lifetime_seconds=_STREAM_LIFETIME_SECONDS
        )
        async with aclosing(events) as order_events:
            async for event in order_events:
                yield OrderStatusChanged.from_domain(event)
```

- **One protocol**: `subscription_protocols=(GRAPHQL_TRANSPORT_WS_PROTOCOL,)`. The default also
  accepts the legacy `graphql-ws`; excluded, it is refused with 4406.
- **`max_subscriptions_per_connection` is 100 by default** and `connection_init_wait_timeout` a
  minute: set both to what a client needs.
- **Exception handlers do not apply to subscription fields.** An exception out of the generator
  is sent as one `errors` payload — masked like any other — followed by `complete`: the
  subscription is over, and the client subscribes again.

## Testing

- **Resolvers are tested through `schema.execute`** with a context of in-memory fakes
  (`testing.md`) — the query, the variables and the context are the test's, and the result's
  `data` and `errors` are asserted. `execute_sync` runs only a schema whose resolvers are all
  `def`; on an `async` one it fails with "GraphQL execution failed to complete synchronously."

```python
async def test_refund_order_answers_foreign_order_as_not_found() -> None:
    order = make_order(owner_id=_OTHER_USER_ID)
    context = make_graphql_context(orders=[order], scopes=frozenset({_REFUND_SCOPE}))

    result = await _SCHEMA.execute(
        _REFUND_ORDER, variable_values={"orderId": str(order.order_id)}, context_value=context
    )

    assert result.errors is None
    assert result.data == {"refundOrder": {"__typename": "OrderNotFound"}}
```

- **The wiring is tested through the app** with the lifespan running — `with TestClient(app)`,
  on `httpx2`, or the async client and `LifespanManager` (`python-fastapi`). Assert the status
  and the body's `data` and `errors`; a GraphQL failure is still a 200.
- **The limits are tested**: a query one level too deep, an alias too many, a `first` over the
  ceiling — each answered with a visible error, not a masked one.

## The Schema Is a Contract

- **The SDL is exported, checked in and compared in CI.** `strawberry export-schema
  shop.graphql.schema:published_schema --output schema.graphql` takes a schema or a
  zero-argument callable; CI exports again and fails on `git diff --exit-code schema.graphql`,
  so every schema change is a diff a reviewer reads in GraphQL.
- **A removal is found by graphql-core, not by eye.** `find_breaking_changes` compares the base
  branch's file with the branch's schema — a removed field, a changed type, a new required
  argument:

```python
published = graphql.build_schema(base_branch_sdl)
current = graphql.build_schema(build_schema(is_introspection_enabled=False).as_str())
breaking_changes = graphql.find_breaking_changes(published, current)
```

- **A field is deprecated before it is removed**: `strawberry.field(deprecation_reason="Use
  totalPrice")` marks it in the SDL and in every client's tooling, and it goes once the traffic
  on it has stopped — counted, not assumed (`python-observability`).
