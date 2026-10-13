# Raw SQL

Injection in general is `python-security`.

### Text is `text()` with bound parameters, and an identifier comes from an allowlist

**Why:** an f-string into query text is injection, and that includes `ORDER BY` and table names,
which cannot be bound parameters — they are chosen from constants. A raw query in a repository is
one the type checker cannot see, so it is kept for reports and migrations.

**Example:**
```python
# WRONG — the sort column comes from the request straight into the SQL
def course_report(*, session: Session, sort_by: str) -> Sequence[Row[Any]]:
    statement = text(f"SELECT title, enrolled FROM course_stats ORDER BY {sort_by}")
    return session.execute(statement).all()


# CORRECT — the column is picked from an allowlist; values travel as bound parameters
_REPORT_SORT_COLUMNS: Final = MappingProxyType({"title": "title", "enrolled": "enrolled DESC"})


def course_report(*, session: Session, sort_by: str, min_enrolled: int) -> Sequence[Row[Any]]:
    order_by = _REPORT_SORT_COLUMNS[sort_by]
    statement = text(
        "SELECT title, enrolled FROM course_stats WHERE enrolled >= :min_enrolled"
        f" ORDER BY {order_by}"  # noqa: S608  # the identifier comes from the allowlist
    )
    return session.execute(statement, {"min_enrolled": min_enrolled}).all()
```
