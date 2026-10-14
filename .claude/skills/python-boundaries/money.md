# Money

### Money is a `Decimal` built from text, inside a value object with its currency

**Why:** a `float` cannot hold `19.99`, and a `Decimal` built from one inherits the error —
`19.989999999999998436805981327779591083526611328125`. Amounts are quantized explicitly at the
boundary — `amount.quantize(Decimal("0.01"), ROUND_HALF_EVEN)` — and wrapped with their currency,
so euros and kroner cannot be added.

**Example:**
```python
# WRONG — built from a float, and carrying no currency
_HARBOUR_DUES: Final = 1.50


def crossing_fare(base_fare: float, *, harbour_dues: float = _HARBOUR_DUES) -> Decimal:
    return Decimal(base_fare + harbour_dues)


# CORRECT — built from the text the amount was written as, with its currency
_HARBOUR_DUES: Final = Fare(amount=Decimal("1.50"), currency=FareCurrency.EUR)


def crossing_fare(base_fare: Fare, *, harbour_dues: Fare = _HARBOUR_DUES) -> Fare:
    return base_fare + harbour_dues
```

### On the wire an amount is a string

**Why:** the reader's JSON parser turns a number into a float before anyone can stop it, and
`19.90` arrives as `19.9`; the string carries the exact digits, and the consumer builds its
`Decimal` from them.
