# Lost Updates

### A read-modify-write is guarded by a version column, and zero rows updated is a conflict

**Why:** two requests that both read version 7 both write, and the second silently erases the
first. The update matches the version it read and increments it; zero rows updated is raised as
its own error and answered by re-reading — never retried blind, which is the lost update again. Row
locks (`SELECT … FOR UPDATE`) are for short transactions that must not fail; the version column is
for edits that span a user's think time.

**Example:**
```sql
-- WRONG — both requests read version 7, and the second write silently erases the first
UPDATE colonies SET frame_count = :frame_count WHERE id = :id;

-- CORRECT — a stale version matches no row, and the repository raises that as a conflict
UPDATE colonies SET frame_count = :frame_count, version = version + 1
WHERE id = :id AND version = :read_version;
```
