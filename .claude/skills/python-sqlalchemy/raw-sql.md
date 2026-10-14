# Raw SQL

### A value in `text()` is a `:name` bound parameter, and a list is an expanding `bindparam`

**Why:** `text()` binds `:name` placeholders from the dict passed to `execute`, whatever the
driver's own placeholder style. A list does not fit one placeholder:
`bindparam(..., expanding=True)` renders one placeholder per element at execution, so the statement
text never holds a value.

**Example:**
```python
# WRONG — the ids are written into the SQL text
def full_course_titles(course_ids: Sequence[int], *, session: Session) -> Sequence[str]:
    id_list = ", ".join(str(course_id) for course_id in course_ids)
    statement = text(f"SELECT title FROM course_stats WHERE is_full AND course_id IN ({id_list})")
    return session.scalars(statement).all()


# CORRECT — the list travels as one expanding parameter
_FULL_COURSE_TITLES: Final = text(
    "SELECT title FROM course_stats WHERE is_full AND course_id IN :course_ids"
).bindparams(bindparam("course_ids", expanding=True))


def full_course_titles(course_ids: Sequence[int], *, session: Session) -> Sequence[str]:
    return session.scalars(_FULL_COURSE_TITLES, {"course_ids": list(course_ids)}).all()
```
