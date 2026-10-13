---
name: python-sqlalchemy
description: >-
  SQLAlchemy 2.0 mechanics: select() and the session, Mapped models, relationship loading, the
  engine and sessionmaker, bulk inserts, upserts, version_id_col, text() with bound parameters. Use
  when code imports sqlalchemy.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# SQLAlchemy

Checked against SQLAlchemy 2.1; the 2.0-style API below is unchanged in 2.1. One use case is one
transaction, opened by the service and never committed by a repository, and a repository returns
frozen domain objects, never ORM rows (`python-persistence`); revisions are `python-alembic`.

## Queries

### A query is `select()` through `session.scalars` or `session.execute`; `Query` is legacy

**Why:** the ORM `Query` object is documented in the source as a legacy construct, and one query
style per codebase is this one. `session.scalars(...)` unwraps whole entities — through
`execute(...)` every row comes back as a one-element `Row`. A primary-key lookup is
`session.get(Course, course_id)`, which answers from the identity map before it queries.

**Example:**
```python
# WRONG — the legacy Query API, and a round trip for a course the session may already hold
def published_courses(*, session: Session) -> list[Course]:
    return session.query(Course).filter(Course.is_published).all()


def course(course_id: int, *, session: Session) -> Course | None:
    return session.query(Course).filter(Course.id == course_id).one_or_none()


# CORRECT — 2.0 style; the identity map answers a primary-key lookup first
def published_courses(*, session: Session) -> list[Course]:
    return list(session.scalars(select(Course).where(Course.is_published)).all())


def course(course_id: int, *, session: Session) -> Course | None:
    return session.get(Course, course_id)
```

### Exactly one row is asked for as exactly one row

**Why:** `.first()` hides a broken query behind a plausible answer — a second certificate for one
enrollment is silently ignored. `.one()` and `.one_or_none()` on `session.scalars(...)`, or
`.scalar_one()` on `session.execute(...)`, raise when the assumption breaks.

**Example:**
```python
# WRONG — a duplicate certificate goes unnoticed
def certificate_for(enrollment_id: int, *, session: Session) -> Certificate | None:
    statement = select(Certificate).where(Certificate.enrollment_id == enrollment_id)
    return session.scalars(statement).first()


# CORRECT — anything but zero or one row raises
def certificate_for(enrollment_id: int, *, session: Session) -> Certificate | None:
    statement = select(Certificate).where(Certificate.enrollment_id == enrollment_id)
    return session.scalars(statement).one_or_none()
```

## Models

### A model is typed with `Mapped[...]`, and a loose annotation gets its column type stated

**Why:** `Mapped` and `mapped_column` give the type checker the shape the ORM sees, and the
annotation carries the nullability — `Mapped[str | None]` is nullable. A bare `Column` gives up
both. The annotation alone picks a loose column: `Mapped[datetime]` becomes a naive `DateTime()`,
`Mapped[Decimal]` a `Numeric()` with no scale — so the column says `DateTime(timezone=True)` and
`Numeric(12, 2)`, or the base's `type_annotation_map` says it once. `Mapped[uuid.UUID]` already maps
to the native `Uuid`.

**Example:**
```python
# WRONG — the checker sees Column on every attribute, and the timestamp is naive
@final
class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    published_at = Column(DateTime)
    price = Column(Numeric)


# CORRECT — typed for the checker, with the time zone and the scale stated
@final
class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2))
```

## Engine and Sessions

### The engine is built once, with a sized pool, `pool_pre_ping` and a statement timeout

**Why:** `pool_pre_ping=True` replaces a connection dropped by a database restart at checkout
instead of failing the request; SQLAlchemy has no portable statement timeout, so it goes through
the driver's `connect_args`. With `postgresql+asyncpg` the engine owns asyncpg's pool and these
rules apply, not `python-asyncpg`'s; asyncpg takes no `options`, so the timeout is
`connect_args={"server_settings": {"statement_timeout": "5000"}}`.

**Example:**
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

### A session is opened in a `with`, and closing it rolls back what the service did not commit

**Why:** the edge opens one session per request or message and the service commits it
(`python-persistence`); a session opened without a `with` is never closed when the use case raises,
and its transaction stays open on its connection. Closing a session rolls back whatever was not
committed, so an error needs no rollback written by hand. `session_factory.begin()` commits on the
way out, which takes the commit away from the service.

**Example:**
```python
# WRONG — an error in the use case skips the close: the transaction stays open on its connection
def handle_enrollment(
    message: EnrollmentRequested, *, session_factory: sessionmaker[Session]
) -> None:
    session = session_factory()
    enroll(message, enrollments=SqlEnrollmentRepository(session), transaction=session)
    session.close()


# CORRECT — closed whatever happens; enroll commits, and anything it did not commit rolls back
def handle_enrollment(
    message: EnrollmentRequested, *, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        enroll(message, enrollments=SqlEnrollmentRepository(session), transaction=session)
```

### A session whose rows are read after commit sets `expire_on_commit=False`

**Why:** `commit()` expires every attribute, and the next read triggers a refresh — which raises
on an async session. With `lazy="raise"` it is not only async: a relationship loaded by
`selectinload` is expired at `commit()` like any attribute, and the next read raises
`InvalidRequestError` (*measured* on 2.1.4). Better still, the repository maps rows to domain
objects before the transaction exits (`python-persistence`).

**Example:**
```python
# WRONG — reading an attribute after commit on an async session raises
def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine)


# CORRECT — attributes keep the values they had at commit
def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

### A repository that needs a generated id flushes; it never commits

**Why:** `commit()` ends the use case's transaction from inside one repository; `flush()`
sends the `INSERT`, fills the primary key, and leaves the transaction open.

**Example:**
```python
# WRONG — commit ends the use case's transaction from inside one repository
@final
class SqlEnrollmentRepository(EnrollmentRepository):
    def __init__(self, *, session: Session) -> None:
        self._session = session

    @override
    def add(self, enrollment: Enrollment) -> EnrollmentId:
        row = EnrollmentRow(course_id=enrollment.course_id, student_id=enrollment.student_id)
        self._session.add(row)
        self._session.commit()
        return EnrollmentId(row.id)


# CORRECT — flush sends the INSERT and fills row.id; the transaction stays open
@final
class SqlEnrollmentRepository(EnrollmentRepository):
    def __init__(self, *, session: Session) -> None:
        self._session = session

    @override
    def add(self, enrollment: Enrollment) -> EnrollmentId:
        row = EnrollmentRow(course_id=enrollment.course_id, student_id=enrollment.student_id)
        self._session.add(row)
        self._session.flush()
        return EnrollmentId(row.id)
```

## Relationships

**Before declaring a `relationship()`, loading one, or asserting how many statements a use case
runs, read [relationships.md](relationships.md)** — `lazy="raise"`, `selectinload` against
`joinedload`, `contains_eager`, a statement-counting fixture.

## Writes

**Before writing many rows, changing rows by a condition, upserting, or adding a version column,
read [writes.md](writes.md)** — `insert()` with a list, one `update()`, the dialect's
`on_conflict_do_update`, `version_id_col` and `StaleDataError`.

## Raw SQL

**Before writing a query as text, read [raw-sql.md](raw-sql.md)** — `text()` with bound
parameters, and identifiers from an allowlist.
