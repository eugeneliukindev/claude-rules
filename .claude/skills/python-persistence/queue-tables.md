# A Table Used as a Queue

### Rows are claimed with `FOR UPDATE SKIP LOCKED`

**Why:** without it every worker waits on the rows the first one locked, and ten workers process
one batch at a time. `SKIP LOCKED` hands each worker rows nobody holds; the claim and the status
change happen in one short transaction, and the work itself runs after it commits.

**Example:**
```sql
-- WRONG — the second worker blocks on the first worker's rows until that transaction ends
SELECT id FROM extraction_jobs WHERE status = 'pending' ORDER BY id LIMIT 10 FOR UPDATE;

-- CORRECT — each worker takes rows nobody holds, and none of them waits
SELECT id FROM extraction_jobs WHERE status = 'pending' ORDER BY id LIMIT 10 FOR UPDATE SKIP LOCKED;
```
