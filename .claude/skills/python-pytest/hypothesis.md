# Property-Based Tests With `hypothesis`

An example test checks the cases its author thought of; a property test states what holds for every
input and lets the library look for the counterexample. Round trips come first — `python-boundaries`
requires `from_dict(to_dict(x)) == x` for every serialized type — then invariants: a constructor
returns a valid object or raises the package's error, a parser never crashes on arbitrary text.

### A strategy is built once, from the domain's own constraints, and a found failure is pinned

**Why:** `st.floats()` brings `NaN`, which never equals itself, and fractions no price was written
as; `st.decimals(places=2, allow_nan=False, allow_infinity=False)` is what money holds. Strategies
are module-level constants. A failure found once is pinned with `@example`, so it reruns even when
the example database — `.hypothesis/`, in `.gitignore` — is gone.

**Example:**
```python
# WRONG — floats bring NaN, which never equals itself, and fractions no price was written as
_MONEY: Final = st.builds(
    Money, amount=st.floats().map(Decimal), currency=st.sampled_from(Currency)
)


# CORRECT — the values money can actually hold, and the one failure ever found, pinned
_MONEY: Final = st.builds(
    Money,
    amount=st.decimals(places=2, allow_nan=False, allow_infinity=False),
    currency=st.sampled_from(Currency),
)


@given(_MONEY)
@example(Money(amount=Decimal("-0.00"), currency=Currency.EUR))
def test_money_round_trips_through_dict(money: Money) -> None:
    assert Money.from_dict(money.to_dict()) == money
```

### CI loads a profile without the deadline

**Why:** the 200 ms default deadline trips at random on a shared runner, so it is a CI hazard, not a
performance test. A profile registered in the root `conftest.py` and loaded by environment turns it
off there.
