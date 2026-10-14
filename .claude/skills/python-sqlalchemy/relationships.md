# Relationships

## Contents

- `lazy="raise"` on every relationship
- `selectinload` for collections, `joinedload` for many-to-one
- `contains_eager` after a join the query already has
- A fixture that counts statements

### Every relationship is declared `lazy="raise"`

**Why:** an unloaded access then raises `InvalidRequestError` naming the relationship, instead of a
page that is quietly a hundred queries. Async sessions refuse implicit lazy loads anyway; designing
as if they always do keeps the sync path correct for free.

**Example:**
```python
# WRONG — one extra query per course, invisible until production
@final
class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    lessons: Mapped[list[Lesson]] = relationship()


# CORRECT — an unloaded access raises; the query states what it loads
@final
class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    lessons: Mapped[list[Lesson]] = relationship(lazy="raise")
```

### A collection loads with `selectinload`, a many-to-one with `joinedload`

**Why:** joining a collection multiplies the parent rows, and 2.0 refuses such a result without
`.unique()`; `selectinload` is a second `IN` query instead. A many-to-one rides the join at no
multiplication. `subqueryload` is the older shape and rarely the right answer now.

**Example:**
```python
# WRONG — the collection is joined and the many-to-one is a second query
def courses_with_lessons(*, session: Session) -> list[Course]:
    statement = select(Course).options(joinedload(Course.lessons), selectinload(Course.instructor))
    return list(session.scalars(statement).all())


# CORRECT — the collection is a second IN query; the many-to-one rides the join
def courses_with_lessons(*, session: Session) -> list[Course]:
    statement = select(Course).options(selectinload(Course.lessons), joinedload(Course.instructor))
    return list(session.scalars(statement).all())
```

### A relationship the query already joined is populated with `contains_eager`

**Why:** `joinedload` after an explicit join adds a second, aliased join to the same table;
`contains_eager` fills the relationship from the columns the query already selects.

**Example:**
```python
# WRONG — joinedload adds a second join to the table the query already joined
def courses_taught_in(country: str, *, session: Session) -> list[Course]:
    statement = (
        select(Course)
        .join(Course.instructor)
        .where(Instructor.country == country)
        .options(joinedload(Course.instructor))
    )
    return list(session.scalars(statement).all())


# CORRECT — the instructor is populated from the join the query already has
def courses_taught_in(country: str, *, session: Session) -> list[Course]:
    statement = (
        select(Course)
        .join(Course.instructor)
        .where(Instructor.country == country)
        .options(contains_eager(Course.instructor))
    )
    return list(session.scalars(statement).all())
```

### Statements are counted with a `before_cursor_execute` listener, per use case

**Why:** `lazy="raise"` stops the implicit N+1; only a count stops the explicit one — a query per
item inside a loop. A fixture records every statement the engine sends, and the test asserts the
number a use case runs.

**Example:**
```python
# WRONG — the test checks the result, so a query per course passes
def test_catalog_page_lists_courses(catalog: CourseCatalog) -> None:
    page = catalog.page(after_course_id=None)

    assert page.courses


# CORRECT — the number of statements is part of what the test pins
@pytest.fixture
def statements(engine: Engine) -> Iterator[list[str]]:
    executed: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        executed.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    yield executed
    event.remove(engine, "before_cursor_execute", record)


def test_catalog_page_runs_two_statements(catalog: CourseCatalog, statements: list[str]) -> None:
    catalog.page(after_course_id=None)

    assert len(statements) == _CATALOG_PAGE_STATEMENTS
```
