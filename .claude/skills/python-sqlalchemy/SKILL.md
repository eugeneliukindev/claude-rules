---
name: python-sqlalchemy
description: >-
  SQLAlchemy 2.0 API: select() with session.execute() and scalars() instead of the legacy Query,
  Mapped and mapped_column models with explicit column types, lazy="raise" relationships with
  selectinload and joinedload, one engine with pool_pre_ping, sessionmaker, expire_on_commit, bulk
  inserts, dialect upserts, optimistic locking with version_id_col, text() with bound parameters.
  Use when Python code imports sqlalchemy; transaction and repository design is in
  python-persistence, migrations in python-migrations and python-alembic.
---

# SQLAlchemy

Assumes 2.0 style. Where a transaction begins and what a repository returns are in
`python-persistence`, revisions in `python-alembic`; this one is how to spell those rules here.

## The 2.0 API — `Query` Is Legacy

`select()` with `session.execute(...)` is the API; the ORM `Query` object is documented in the
source as a legacy construct. One query style per codebase, and it is this one:

```python
# WRONG — legacy Query API
users = session.query(User).filter(User.is_active).all()

# CORRECT — 2.0 style
users = session.scalars(select(User).where(User.is_active)).all()
```

- **`session.scalars(...)` when selecting whole entities** — shorthand for
  `session.execute(...).scalars()`. Without it every row comes back as a one-element `Row`.

```python
# WRONG — each element is a one-element Row, not a User
users = session.execute(select(User).where(User.is_active)).all()

# CORRECT — scalars() unwraps the entity
users = session.scalars(select(User).where(User.is_active)).all()
```

- **`session.get(User, user_id)` for a primary-key lookup** — it checks the identity map first and
  skips the query when the object is already loaded.

```python
# WRONG — a round trip every time, even for a user this session already holds
user = session.scalars(select(User).where(User.id == user_id)).one_or_none()

# CORRECT — the identity map answers first
user = session.get(User, user_id)
```

- **`.scalar_one()` / `.scalar_one_or_none()` when exactly one row is the contract.** `.first()`
  hides a broken query behind a plausible answer; `scalar_one()` raises when the assumption breaks.

```python
# WRONG — a second invoice for the order is silently ignored
invoice = session.scalars(select(Invoice).where(Invoice.order_id == order_id)).first()

# CORRECT — one() on scalars(), scalar_one() on execute(): anything but one row raises
invoice = session.scalars(select(Invoice).where(Invoice.order_id == order_id)).one()
```

## Declarative Models

- **`Mapped[...]` and `mapped_column(...)`**, so the model is typed and the type checker sees the
  same shape the ORM does. A bare `Column` gives up both.
- **Optionality is in the annotation**: `Mapped[str]` is `NOT NULL`, `Mapped[str | None]` is
  nullable. Do not restate it with `nullable=` unless overriding.

```python
# WRONG — the checker sees Column[str] on every row, and never that nickname can be None
@final
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    nickname = Column(String)

# CORRECT — the annotation is the type and the nullability, for the checker and the ORM alike
@final
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str]
    nickname: Mapped[str | None]
```

- **The annotation alone picks the loose column type.** `Mapped[datetime]` becomes a naive
  `DateTime()` and `Mapped[Decimal]` a `Numeric()` with no scale. Spell
  `mapped_column(DateTime(timezone=True))` and `Numeric(12, 2)`, or set them once in the base's
  `type_annotation_map`. `Mapped[uuid.UUID]` already maps to the native `Uuid`; `Float` is never
  money.

```python
# WRONG — TIMESTAMP WITHOUT TIME ZONE and a NUMERIC that keeps whatever scale it is given
created_at: Mapped[datetime]
total: Mapped[Decimal]

# CORRECT — the column states the time zone and the scale
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
total: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2))
```

## Loading — Make N+1 Impossible, Not Unlikely

- **Set `lazy="raise"` on relationships.** Then an unloaded access raises `InvalidRequestError`
  naming the relationship, instead of a page that is quietly a hundred queries. This is the single
  highest-value setting in the library.

```python
# WRONG — one extra query per order, invisible until production
items: Mapped[list[OrderItem]] = relationship()
...
orders = session.scalars(select(Order)).all()
totals = [order_total(order.items) for order in orders]
# CORRECT — unloaded access raises; the query states what it loads
items: Mapped[list[OrderItem]] = relationship(lazy="raise")
...
orders = session.scalars(select(Order).options(selectinload(Order.items))).all()
totals = [order_total(order.items) for order in orders]
```

- **Load explicitly at the query**: `selectinload` for collections (a second `IN` query),
  `joinedload` for many-to-one (one join). `subqueryload` is the older shape and rarely the right
  answer now.

```python
# WRONG — joining a collection multiplies rows, and 2.0 refuses the result without .unique()
orders = session.scalars(
    select(Order).options(joinedload(Order.items), selectinload(Order.customer))
).all()

# CORRECT — the collection is a second IN query; the many-to-one rides the join
orders = session.scalars(
    select(Order).options(selectinload(Order.items), joinedload(Order.customer))
).all()
```

- **`contains_eager` when you have already joined** and want the ORM to populate from those columns
  rather than issuing another query.

```python
# WRONG — joinedload adds a second, aliased join to the table the query already joined
orders = session.scalars(
    select(Order)
    .join(Order.customer)
    .where(Customer.country == country)
    .options(joinedload(Order.customer))
).all()

# CORRECT — the customer is populated from the join the query already has
orders = session.scalars(
    select(Order)
    .join(Order.customer)
    .where(Customer.country == country)
    .options(contains_eager(Order.customer))
).all()
```

- Async sessions refuse implicit lazy loads anyway — design as if they always do, and the sync path
  stays correct for free.

## Engine and Sessions

- **The engine is built once** in the composition root: explicit `pool_size`, `pool_pre_ping=True`
  so a connection dropped by a database restart is replaced at checkout instead of failing the
  request, and a statement timeout passed through the driver's `connect_args` — SQLAlchemy has no
  portable one.

```python
# WRONG — default pool size, dead connections handed out after a restart, no statement limit
def build_engine(database_url: str, *, pool_size: int, statement_timeout_ms: int) -> Engine:
    return create_engine(database_url)

# CORRECT — a sized pool checked at checkout, and the timeout in the driver's (psycopg) options
def build_engine(database_url: str, *, pool_size: int, statement_timeout_ms: int) -> Engine:
    return create_engine(
        database_url,
        pool_size=pool_size,
        pool_pre_ping=True,
        connect_args={"options": f"-c statement_timeout={statement_timeout_ms}"},
    )
```

- **One `sessionmaker` next to the engine**; the Unit of Work opens a session per use case with
  `with session_factory.begin() as session:`, which commits on clean exit and rolls back on error.

```python
# WRONG — an error in the use case skips commit and leaves the transaction open on its connection
@contextmanager
def open_unit_of_work(session_factory: sessionmaker[Session]) -> Iterator[UnitOfWork]:
    session = session_factory()
    yield UnitOfWork(orders=SqlAlchemyOrderRepository(session))
    session.commit()

# CORRECT — begin() commits on clean exit, rolls back on error and closes the session either way
@contextmanager
def open_unit_of_work(session_factory: sessionmaker[Session]) -> Iterator[UnitOfWork]:
    with session_factory.begin() as session:
        yield UnitOfWork(orders=SqlAlchemyOrderRepository(session))
```

- **`expire_on_commit=False`** for async and for any code that reads attributes after commit;
  otherwise the first attribute access after `commit()` triggers a refresh — which, on an async
  session, raises.

```python
# WRONG — commit expires every attribute, and reading one afterwards on an async session raises
session_factory = async_sessionmaker(engine)

# CORRECT — attributes keep the values they had at commit
session_factory = async_sessionmaker(engine, expire_on_commit=False)
```

- **`session.flush()` when a repository needs the generated id** inside the transaction — never
  `commit()`, which ends the Unit of Work's transaction from inside it.

```python
# WRONG — commit ends the unit of work's transaction from inside one repository
def add(self, order: Order) -> OrderId:
    row = OrderRow(customer_id=order.customer_id, total=order.total)
    self._session.add(row)
    self._session.commit()
    return OrderId(row.id)

# CORRECT — flush sends the INSERT and fills row.id; the transaction stays open
def add(self, order: Order) -> OrderId:
    row = OrderRow(customer_id=order.customer_id, total=order.total)
    self._session.add(row)
    self._session.flush()
    return OrderId(row.id)
```

## Writing

- **Bulk insert is `session.execute(insert(Order), rows)`** with a list of dicts, which the
  dialect batches; a set-based change is one `update(Order).where(...).values(...)`. Not a loop of
  `session.add()`.

```python
# WRONG — loads every expired order to change one column, then writes each row back
for order in session.scalars(select(Order).where(Order.expires_at < now)):
    order.status = OrderStatus.EXPIRED

# CORRECT — one UPDATE; the rows change where they are
session.execute(update(Order).where(Order.expires_at < now).values(status=OrderStatus.EXPIRED))
```

- **Upsert through the dialect's `insert(...).on_conflict_do_update(...)`** (PostgreSQL, SQLite;
  `on_duplicate_key_update` on MySQL) rather than a select-then-insert race.

```python
# WRONG — two requests both find no row, and the second INSERT fails on the unique key
stock = session.scalars(select(StockLevel).where(StockLevel.sku == sku)).one_or_none()
if stock is None:
    session.add(StockLevel(sku=sku, quantity=quantity))
else:
    stock.quantity = quantity

# CORRECT — one statement; the database settles the conflict atomically
statement = insert(StockLevel).values(sku=sku, quantity=quantity)
session.execute(
    statement.on_conflict_do_update(
        index_elements=[StockLevel.sku], set_={"quantity": statement.excluded.quantity}
    )
)
```

- **`.returning(...)`** to get the written rows back in the same round trip.
- **Optimistic locking is `__mapper_args__ = {"version_id_col": version}`** after
  `version: Mapped[int] = mapped_column()` — the assignment is what binds the name the mapper
  arguments refer to. Every ORM update then carries the version check and increment, and
  a stale write raises `StaleDataError`, which the repository translates into the domain's conflict
  error (`python-persistence`). It covers ORM flushes only — a bulk `update()` checks nothing
  unless it states the version in its own `where`.

```python
# WRONG — an annotation alone binds no name, so the class body raises NameError
@final
class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int]
    __mapper_args__ = {"version_id_col": version}

# CORRECT — the assignment binds the column the mapper arguments name
@final
class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column()
    __mapper_args__ = {"version_id_col": version}
```

## Raw SQL

- **`text()` with bound parameters, always.** Never an f-string into query text — including
  `ORDER BY` and table names, which are chosen from a whitelist of constants.
- Raw SQL is for reports and migrations. A raw query in a repository is a query the type checker
  cannot see.
