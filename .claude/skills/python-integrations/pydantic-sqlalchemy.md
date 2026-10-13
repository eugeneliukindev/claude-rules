# pydantic and SQLAlchemy

The seam between `python-pydantic` and `python-sqlalchemy`, linked from both skills.

### A model is never validated from an ORM row with `from_attributes`

**Why:** `from_attributes=True` reads the row attribute by attribute, so every relationship the
model names is loaded there: a `lazy="raise"` relationship raises far from the query, and one left
lazy runs a statement per row. The repository turns the row into a domain object, and the model is
built from that, field by field (`python-boundaries`).

**Example:**
```python
# WRONG — validating the row loads its lessons here, one statement per course, or raises
class CourseResponse(BoundaryModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    lesson_titles: tuple[str, ...]


def course_response(row: CourseRow) -> CourseResponse:
    return CourseResponse.model_validate(row)


# CORRECT — the domain object, loaded by the repository, is what the model is built from
class CourseResponse(BoundaryModel):
    title: str
    lesson_titles: tuple[str, ...]

    @classmethod
    def from_domain(cls, course: Course) -> Self:
        lesson_titles = tuple(lesson.title for lesson in course.lessons)
        return cls(title=course.title, lesson_titles=lesson_titles)
```
