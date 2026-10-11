# Writes

## Contents

- Many rows through one `insert()`; a set-based change through one `update()`
- An upsert through the dialect's `on_conflict_do_update`
- Optimistic locking with `version_id_col`

### Many rows are one `insert()` with a list, and a set-based change is one `update()`

**Why:** a loop of `session.add()` pays an ORM object, an identity-map entry and change tracking per
row, and may send one `INSERT` per row; a loop over loaded rows reads every row first and then
writes each one back. `.returning(...)` gets the written rows back in the same round trip.

**Example:**
```python
# WRONG — loads every expired enrollment to change one column, then writes each row back
def expire_enrollments(session: Session, *, now: datetime) -> None:
    expired = select(EnrollmentRow).where(EnrollmentRow.expires_at < now)
    for enrollment in session.scalars(expired):
        enrollment.status = EnrollmentStatus.EXPIRED


# CORRECT — one UPDATE; the rows change where they are
def expire_enrollments(session: Session, *, now: datetime) -> None:
    session.execute(
        update(EnrollmentRow)
        .where(EnrollmentRow.expires_at < now)
        .values(status=EnrollmentStatus.EXPIRED)
    )
```

### An upsert is the dialect's `insert(...).on_conflict_do_update(...)`

**Why:** a select-then-insert is passed by two concurrent requests alike, and the second `INSERT`
fails on the unique key (`python-persistence`). PostgreSQL and SQLite spell it
`on_conflict_do_update`, MySQL `on_duplicate_key_update`; the `insert` is the dialect's, from
`sqlalchemy.dialects.postgresql`.

**Example:**
```python
# WRONG — two requests both find no row, and the second INSERT fails on the unique key
def record_progress(session: Session, *, student_id: int, lesson_id: int, percent: int) -> None:
    progress = session.scalars(
        select(LessonProgress).where(
            LessonProgress.student_id == student_id, LessonProgress.lesson_id == lesson_id
        )
    ).one_or_none()
    if progress is None:
        session.add(LessonProgress(student_id=student_id, lesson_id=lesson_id, percent=percent))
    else:
        progress.percent = percent


# CORRECT — one statement; the database settles the conflict atomically
def record_progress(session: Session, *, student_id: int, lesson_id: int, percent: int) -> None:
    statement = insert(LessonProgress).values(
        student_id=student_id, lesson_id=lesson_id, percent=percent
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[LessonProgress.student_id, LessonProgress.lesson_id],
            set_={"percent": statement.excluded.percent},
        )
    )
```

### Optimistic locking is `version_id_col` on an assigned column

**Why:** every ORM update then carries the version check and increment, and a stale write raises
`StaleDataError`, which the repository translates into the domain's conflict error
(`python-persistence`). The column must be assigned — an annotation alone binds no name, and the
class body raises `NameError`. It covers ORM flushes only: a bulk `update()` checks nothing unless
its own `where` states the version.

**Example:**
```python
# WRONG — an annotation alone binds no name, so the class body raises NameError
@final
class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int]
    __mapper_args__ = {"version_id_col": version}


# CORRECT — the assignment binds the column the mapper arguments name
@final
class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column()
    __mapper_args__ = {"version_id_col": version}
```
