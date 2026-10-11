# Money

### Money is a `Decimal` built from text, inside a value object with its currency

**Why:** a `float` cannot hold `19.99`, and a `Decimal` built from one inherits the error —
`19.989999999999998436805981327779591083526611328125`. Amounts are quantized explicitly at the
boundary — `amount.quantize(Decimal("0.01"), ROUND_HALF_EVEN)` — and wrapped with their currency,
so euros and dollars cannot be added.

**Example:**
```python
# WRONG — built from a float, and carrying no currency
_BOOKING_FEE: Final = 1.50


def ticket_price(base_price: float, *, fee: float = _BOOKING_FEE) -> Decimal:
    return Decimal(base_price + fee)


# CORRECT — built from the text the amount was written as, with its currency
_BOOKING_FEE: Final = Money(amount=Decimal("1.50"), currency=Currency.EUR)


def ticket_price(base_price: Money, *, fee: Money = _BOOKING_FEE) -> Money:
    return base_price + fee
```

### On the wire an amount is a string

**Why:** the reader's JSON parser turns a number into a float before anyone can stop it, and
`19.90` arrives as `19.9`; the string carries the exact digits, and the consumer builds its
`Decimal` from them.

**Example:**
```python
# WRONG — the consumer's parser makes a float of it
def to_payload(price: Money) -> dict[str, object]:
    return {"amount": float(price.amount), "currency": price.currency}


# CORRECT — the exact digits travel
def to_payload(price: Money) -> dict[str, object]:
    return {"amount": str(price.amount), "currency": price.currency}
```
