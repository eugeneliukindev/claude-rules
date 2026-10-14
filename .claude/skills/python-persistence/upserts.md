# Idempotent Inserts

### An idempotent insert is one `INSERT … ON CONFLICT` on the unique key

**Why:** a `SELECT` for the key followed by an `INSERT` is passed by two concurrent deliveries
alike, and the second then fails on what was a harmless repeat. The unique key decides atomically;
`DO NOTHING RETURNING` returns no row for a duplicate, which is how the caller tells the two apart.

**Example:**
```sql
-- WRONG — both deliveries find no row; the second INSERT then fails on the primary key
SELECT 1 FROM honey_harvests WHERE harvest_id = :harvest_id;
INSERT INTO honey_harvests (harvest_id, honey_grams) VALUES (:harvest_id, :honey_grams);

-- CORRECT — the unique key decides atomically; an empty result means "already recorded"
INSERT INTO honey_harvests (harvest_id, honey_grams) VALUES (:harvest_id, :honey_grams)
ON CONFLICT (harvest_id) DO NOTHING RETURNING harvest_id;
```
