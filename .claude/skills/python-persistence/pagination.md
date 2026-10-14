# Pagination

### Pages are keyset, from the last key the caller saw

**Why:** `OFFSET 100000` reads and throws away a hundred thousand rows for every page, so the last
page costs the most and the cost grows with the table — and a row inserted between two requests
shifts every later page, showing one row twice or skipping one. A keyset page continues from the
last key, with a unique tiebreaker and an index in exactly that order.
**Except:** a small, bounded list where jumping to page N is the feature.

**Example:**
```sql
-- WRONG — the database reads and discards every row before the page
SELECT id, inspected_at, colony_id FROM hive_inspections ORDER BY inspected_at, id
LIMIT 50 OFFSET 100000;

-- CORRECT — the index on (inspected_at, id) seeks straight to the last row the caller saw
SELECT id, inspected_at, colony_id FROM hive_inspections
WHERE (inspected_at, id) > (:last_inspected_at, :last_id)
ORDER BY inspected_at, id LIMIT 50;
```
