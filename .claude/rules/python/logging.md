---
paths:
  - "**/*.py"
---

# Python - Logging

### No secret or personal data in a log; identifiers go in `extra=`, not into the message

**Why:** tokens, passwords, card numbers and raw request payloads in logs leak to everyone who reads
them; an identifier formatted into the message is a string a search cannot filter on. `ERROR` is
for what someone must look at, never an expected user mistake.

**Example:**
```python
# WRONG - the whole payment, card number included, formatted into the text
logger.info(f"payment captured: {payment}")


# CORRECT - the identifiers as fields, and nothing a reader should not see
logger.info("payment captured", extra={"payment_id": payment.payment_id, "amount": payment.amount})
```
