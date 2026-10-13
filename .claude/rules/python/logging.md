---
paths:
  - "**/*.py"
---

# Python — Logging

Where logging is configured and the format it writes are `python-observability`.

### One logger per module, from `getLogger(__name__)`; `ERROR` only when someone must look

**Why:** the module name is what lets a handler filter by package; `ERROR` that also fires for an
expected user mistake trains everyone to ignore it.

**Example:**
```python
# WRONG — a shared named logger, and ERROR for a customer typing a wrong code
log = logging.getLogger("app")


def apply_discount(code: str, *, discounts: DiscountRepository) -> Discount:
    discount = discounts.find(code)
    if discount is None:
        log.error("discount not found", extra={"code": code})
        raise UnknownDiscountError(code)
    return discount


# CORRECT — the module's own logger, and INFO for an expected outcome
logger = logging.getLogger(__name__)


def apply_discount(code: str, *, discounts: DiscountRepository) -> Discount:
    discount = discounts.find(code)
    if discount is None:
        logger.info("discount code unknown", extra={"code_length": len(code)})
        raise UnknownDiscountError(code)
    return discount
```

### No secret or personal data in a log; identifiers go in `extra=`, not into the message

**Why:** tokens, passwords, card numbers and raw request payloads in logs leak to everyone who reads
them; an identifier formatted into the message is a string a search cannot filter on.

**Example:**
```python
# WRONG — the whole payment, card number included, formatted into the text
logger.info(f"payment captured: {payment}")


# CORRECT — the identifiers as fields, and nothing a reader should not see
logger.info("payment captured", extra={"payment_id": payment.payment_id, "amount": payment.amount})
```

### A message is the event, lower-case, present tense, without punctuation

**Why:** `"payment captured"` reads and greps the same in every module; `"Captured the payment
successfully!"` is the same event in a spelling nobody searches for.

### Timing and counting are metrics, not log lines

**Why:** a log line per event in a hot loop costs I/O on every iteration and is still not a number a
dashboard can sum (`python-observability`).
