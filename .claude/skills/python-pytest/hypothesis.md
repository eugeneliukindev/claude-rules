# Property-Based Tests With `hypothesis`

An example test checks the cases its author thought of; a property test states what holds for every
input and lets the library look for the counterexample. Round trips come first — a value serialized
and parsed back equals itself — then invariants: a constructor returns a valid object or raises the
package's error, a parser never crashes on arbitrary text.

### A strategy is built once, from the domain's own bounds, and a found failure is pinned

**Why:** a bare `st.floats()` brings `NaN`, which never equals itself, and infinities no value of
the domain holds; given `min_value` and `max_value`, `st.floats` leaves both out. Strategies are
module-level constants. A failure found once is pinned with `@example`, so it reruns even when the
example database — `.hypothesis/`, in `.gitignore` — is gone.

**Example:**
```python
# WRONG — NaN and infinity, which no ease factor holds, and the bound that once failed not pinned
_EASE_FACTORS: Final = st.floats()


@given(ease_factor=_EASE_FACTORS, grade=st.sampled_from(RecallGrade))
def test_review_keeps_ease_factor_in_bounds(ease_factor: float, grade: RecallGrade) -> None:
    reviewed = review_card(make_card(ease_factor=ease_factor), grade=grade)

    assert MIN_EASE_FACTOR <= reviewed.ease_factor <= MAX_EASE_FACTOR


# CORRECT — the bounds the scheduler keeps, and the one failure ever found, pinned
_EASE_FACTORS: Final = st.floats(min_value=MIN_EASE_FACTOR, max_value=MAX_EASE_FACTOR)


@given(ease_factor=_EASE_FACTORS, grade=st.sampled_from(RecallGrade))
@example(ease_factor=MIN_EASE_FACTOR, grade=RecallGrade.FORGOTTEN)
def test_review_keeps_ease_factor_in_bounds(ease_factor: float, grade: RecallGrade) -> None:
    reviewed = review_card(make_card(ease_factor=ease_factor), grade=grade)

    assert MIN_EASE_FACTOR <= reviewed.ease_factor <= MAX_EASE_FACTOR
```

### CI loads a profile without the deadline

**Why:** the 200 ms default deadline trips at random on a shared runner, so it is a CI hazard, not a
performance test. A profile registered in the root `conftest.py` —
`settings.register_profile("ci", deadline=None)` — and loaded by environment turns it off there.
