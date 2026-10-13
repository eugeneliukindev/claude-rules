---
paths:
  - "**/*.py"
---

# Python — Errors

## What Is an Error

### `None` is for lookups where absence is normal; a promised value raises

**Why:** `-> User | None` makes every caller handle absence, which is right for a search; a
signature promising a value that returns `None`, `False`, `-1` or an empty list on failure lets the
caller carry on with nonsense.

**Example:**
```python
# WRONG — "no rate" and "rate service down" look the same
def exchange_rate(source: Currency, target: Currency, *, rates: RateService) -> Decimal | None:
    try:
        return rates.fetch(source, target)
    except RateServiceError:
        return None


# CORRECT — a lookup that may legitimately find nothing says so; a failure raises
def find_user(email: str, *, users: UserRepository) -> User | None:
    return users.find_by_email(email)
```

### An outcome the caller would treat as success is not an error

**Why:** `cancel` on a cancelled booking and `delete` of a missing key promise a state, and they
succeed — a retry then needs no special case (`python-boundaries`).
**Except:** never a guess in place of an error — a clipped index, an empty list for "not found".

**Example:**
```python
# WRONG — the second cancel, from a retry, fails a call that already got what it asked for
def cancel_booking(booking_id: BookingId, *, bookings: BookingRepository) -> None:
    booking = bookings.get(booking_id)
    if booking.status is BookingStatus.CANCELLED:
        raise BookingAlreadyCancelledError(booking_id)
    bookings.save(replace(booking, status=BookingStatus.CANCELLED))


# CORRECT — "cancelled afterwards" holds after a repeat too
def cancel_booking(booking_id: BookingId, *, bookings: BookingRepository) -> None:
    booking = bookings.get(booking_id)
    if booking.status is BookingStatus.CANCELLED:
        return
    bookings.save(replace(booking, status=BookingStatus.CANCELLED))
```


## Raising

### A failure is caught narrowly, translated with its cause, and never returned as `None`

**Why:** the four broken most often, together: a broad `except` swallows the bug along with the
expected failure, a `try` around everything hides which line failed, a driver's error re-raised
without `from` loses its cause, and `None` for an error makes every caller guess.

**Example:**
```python
# WRONG — broad catch, swallowed cause, a try around everything, the error returned as None
def load_user(user_id: UserId, *, base_url: str) -> User | None:
    try:
        with urlopen(f"{base_url}/users/{user_id}", timeout=_TIMEOUT_SECONDS) as response:
            return User.from_payload(json.load(response))
    except Exception:
        logger.error("failed")
        return None


# CORRECT — narrow try, translated with its cause, an error is never a return value
def load_user(user_id: UserId, *, base_url: str) -> User:
    try:
        with urlopen(f"{base_url}/users/{user_id}", timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code == HTTPStatus.NOT_FOUND:
            raise UserNotFoundError(user_id) from error
        raise UserServiceError(f"Fetching user {user_id} failed") from error
    return User.from_payload(payload)
```

### A message carries the identifying values, and the exception carries them as attributes

**Why:** `"Bad ticket"` in a log names nothing a reader can look up; a handler that has to parse
the text to learn which ticket failed breaks when the wording changes.

**Example:**
```python
# WRONG — nothing to search for, nothing to read programmatically
class TicketNotTransferableError(TicketingError):
    pass


raise TicketNotTransferableError("Bad ticket")


# CORRECT — the values in the message and on the object
class TicketNotTransferableError(TicketingError):
    def __init__(self, ticket_id: TicketId, *, event_starts_at: datetime) -> None:
        super().__init__(f"Ticket {ticket_id} cannot be transferred after {event_starts_at}")
        self.ticket_id = ticket_id
        self.event_starts_at = event_starts_at
```

## The Hierarchy

### Every package defines one root exception, named for the package

**Why:** `BillingError(Exception)` lets a caller catch "anything from billing" with one clause; a
package whose errors inherit `Exception` directly leaves it to list them all, and miss the next.

### A leaf class is earned by a caller who catches it, and inherits the stdlib type it expects

**Why:** until a caller catches it alone, the nearest category with the identifying values is
enough. A leaf names the failure without the prefix (`naming.md`) and inherits `LookupError`,
`ValueError` or `TypeError` where stdlib code catches it — a missing key from a `Mapping`'s
`__getitem__` must be a `KeyError`, or `in` and `.get()` break.
**Except:** never an `OSError` subtype — `PermissionError`, `TimeoutError`, `FileNotFoundError`
carry errno semantics, and an `except OSError` around a socket swallows the domain failure.

**Example:**
```python
# WRONG — PermissionError is an OSError: `except OSError` around file handling now takes it
class AccessDeniedError(CatalogError, PermissionError): ...


# CORRECT — the errno family stays the operating system's
class AccessDeniedError(CatalogError): ...


# CORRECT — a Mapping's missing key is a KeyError, so `in` and `.get()` keep working
class ProductNotFoundError(CatalogError, KeyError): ...


@final
class ProductIndex(Mapping[Sku, Product]):
    def __init__(self, products: Iterable[Product]) -> None:
        self._product_by_sku = {product.sku: product for product in products}

    @override
    def __getitem__(self, sku: Sku) -> Product:
        try:
            return self._product_by_sku[sku]
        except KeyError as error:
            raise ProductNotFoundError(sku) from error

    @override
    def __iter__(self) -> Iterator[Sku]:
        return iter(self._product_by_sku)

    @override
    def __len__(self) -> int:
        return len(self._product_by_sku)
```

## Handling

### EAFP when the failure is rare and checking would race; LBYL when the check is cheap and atomic

**Why:** checking a file exists and then opening it races with whoever deletes it; catching a
`KeyError` for the common case is slower and hides the expected path. Never both for one operation.

### An error is caught where it can be handled, and logged once there

**Why:** retry, fall back, convert or report — a layer that can only log and re-raise adds a second
log line for the same failure and handles nothing.

**Example:**
```python
# WRONG — logged here, re-raised, and logged again by whoever handles it
def charge(invoice: Invoice, *, gateway: PaymentGateway) -> Receipt:
    try:
        return gateway.charge(invoice.number, invoice.total)
    except PaymentDeclinedError:
        logger.exception("charge failed", extra={"invoice_number": invoice.number})
        raise


# CORRECT — no try at all; the boundary that decides what to do logs it once
def charge(invoice: Invoice, *, gateway: PaymentGateway) -> Receipt:
    return gateway.charge(invoice.number, invoice.total)
```
