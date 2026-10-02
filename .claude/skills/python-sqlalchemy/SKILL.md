---
name: python-sqlalchemy
description: >-
  SQLAlchemy 2.0 and alembic API: select() with session.execute() and scalars() instead of the
  legacy Query, Mapped and mapped_column models with explicit column types, lazy="raise"
  relationships with selectinload and joinedload, one engine with pool_pre_ping, sessionmaker and
  expire_on_commit, bulk inserts and dialect upserts, text() with bound parameters, and alembic
  autogenerate limits and revision mechanics. Use when Python code imports sqlalchemy or alembic;
  transaction, repository and migration design is in python-persistence.
---

# SQLAlchemy

Assumes 2.0 style. Where a transaction begins, what a repository returns and how a migration is
planned are in the `python-persistence` skill; this one is how to spell those rules here.

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
- **`session.get(User, user_id)` for a primary-key lookup** — it checks the identity map first and
  skips the query when the object is already loaded.
- **`.scalar_one()` / `.scalar_one_or_none()` when exactly one row is the contract.** `.first()`
  hides a broken query behind a plausible answer; `scalar_one()` raises when the assumption breaks.

## Declarative Models

- **`Mapped[...]` and `mapped_column(...)`**, so the model is typed and the type checker sees the
  same shape the ORM does. A bare `Column` gives up both.
- **Optionality is in the annotation**: `Mapped[str]` is `NOT NULL`, `Mapped[str | None]` is
  nullable. Do not restate it with `nullable=` unless overriding.
- **The annotation alone picks the loose column type.** `Mapped[datetime]` becomes a naive
  `DateTime()` and `Mapped[Decimal]` a `Numeric()` with no scale. Spell
  `mapped_column(DateTime(timezone=True))` and `Numeric(12, 2)`, or set them once in the base's
  `type_annotation_map`. `Mapped[uuid.UUID]` already maps to the native `Uuid`; `Float` is never
  money.

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
- **`contains_eager` when you have already joined** and want the ORM to populate from those columns
  rather than issuing another query.
- Async sessions refuse implicit lazy loads anyway — design as if they always do, and the sync path
  stays correct for free.

## Engine and Sessions

- **The engine is built once** in the composition root: explicit `pool_size`, `pool_pre_ping=True`
  so a connection dropped by a database restart is replaced at checkout instead of failing the
  request, and a statement timeout passed through the driver's `connect_args` — SQLAlchemy has no
  portable one.
- **One `sessionmaker` next to the engine**; the Unit of Work opens a session per use case with
  `with session_factory.begin() as session:`, which commits on clean exit and rolls back on error.
- **`expire_on_commit=False`** for async and for any code that reads attributes after commit;
  otherwise the first attribute access after `commit()` triggers a refresh — which, on an async
  session, raises.
- **`session.flush()` when a repository needs the generated id** inside the transaction — never
  `commit()`, which ends the Unit of Work's transaction from inside it.

## Writing

- **Bulk insert is `session.execute(insert(Order), rows)`** with a list of dicts, which the
  dialect batches; a set-based change is one `update(Order).where(...).values(...)`. Not a loop of
  `session.add()`.
- **Upsert through the dialect's `insert(...).on_conflict_do_update(...)`** (PostgreSQL, SQLite;
  `on_duplicate_key_update` on MySQL) rather than a select-then-insert race.
- **`.returning(...)`** to get the written rows back in the same round trip.

## Raw SQL

- **`text()` with bound parameters, always.** Never an f-string into query text — including
  `ORDER BY` and table names, which are chosen from a whitelist of constants.
- Raw SQL is for reports and migrations. A raw query in a repository is a query the type checker
  cannot see.

## Alembic

- **Autogenerate misses** table and column renames (it emits a drop plus an add), anonymously
  named constraints, and server-default changes unless `compare_server_default=True`. Give the
  `MetaData` a `naming_convention` so every constraint has a name autogenerate can diff and a
  downgrade can drop.
- **Inline tables, not the app's models**: `sa.table("orders", sa.column("status", sa.String))`
  with `op.execute(...)` for any data a revision touches.
- **`CREATE INDEX CONCURRENTLY` cannot run in a transaction**: wrap
  `op.create_index(..., postgresql_concurrently=True)` in
  `with op.get_context().autocommit_block():`, which commits everything before it.
- **`alembic check` in CI** fails on drift between models and revisions; `alembic upgrade head`
  then `alembic downgrade base` on an empty database exercises the chain.
