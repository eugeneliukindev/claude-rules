# PgBouncer

### Behind PgBouncer in transaction mode, prepared statements are tracked by PgBouncer or not cached

**Why:** asyncpg prepares every statement as a named, protocol-level prepared statement and keeps
up to `statement_cache_size=100` of them per connection. In transaction mode the next transaction
may run on another server connection, where the statement does not exist:
`InvalidSQLStatementNameError` or `DuplicatePreparedStatementError`, under load only — never in
development, where there is no PgBouncer. PgBouncer 1.21+ with `max_prepared_statements` above
zero (the default from 1.24) re-prepares them and the cache keeps working; otherwise the pool sets
`statement_cache_size=0`, and every call parses, plans and prepares again. A session-level `SET`,
`LISTEN` and an advisory lock do not survive between transactions there either.

**Example:**
```ini
; WRONG — transaction pooling with prepared-statement tracking off: errors under load only
[pgbouncer]
pool_mode = transaction
max_prepared_statements = 0

; CORRECT — PgBouncer tracks and re-prepares asyncpg's statements
[pgbouncer]
pool_mode = transaction
max_prepared_statements = 200
```
