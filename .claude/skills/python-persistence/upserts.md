# Idempotent Inserts

Why a write that may repeat must be idempotent is `python-boundaries`; the dialect spelling of an
upsert in an ORM is in its library skill.

### An idempotent insert is one `INSERT … ON CONFLICT` on the unique key

**Why:** a `SELECT` for the key followed by an `INSERT` is passed by two concurrent deliveries
alike, and the second then fails on what was a harmless repeat. The unique key decides atomically;
`DO NOTHING RETURNING` returns no row for a duplicate, which is how the caller tells the two apart.

**Example:**
```sql
-- WRONG — both deliveries find no row; the second INSERT then fails on the primary key
SELECT 1 FROM payments WHERE payment_id = :payment_id;
INSERT INTO payments (payment_id, amount) VALUES (:payment_id, :amount);

-- CORRECT — the unique key decides atomically; an empty result means "already recorded"
INSERT INTO payments (payment_id, amount) VALUES (:payment_id, :amount)
ON CONFLICT (payment_id) DO NOTHING RETURNING payment_id;
```
