# Bulk Writes

### Many plain rows go through `copy_records_to_table`; rows that need SQL, `executemany`

**Why:** a loop of `execute` is a round trip per row. `copy_records_to_table` is `COPY`, far faster
than inserts, inside the use case's transaction when it must be all or nothing; it cannot
upsert or return rows, and asyncpg quotes the table and column names itself. `executemany` fits a
row that needs `ON CONFLICT`, an expression or a lookup: one prepared statement, the rows pipelined,
and atomic since 0.22 — a failing row leaves none of the others.

**Example:**
```python
# WRONG — one round trip per pairing: a round of two hundred boards is two hundred statements
async def record_pairings(
    pairings: Sequence[Pairing], *, connection: PoolConnectionProxy
) -> None:
    for pairing in pairings:
        await connection.execute(
            _INSERT_PAIRING, pairing.round_id, pairing.board, pairing.white_id, pairing.black_id
        )


# CORRECT — one COPY streams every pairing
async def record_pairings(
    pairings: Sequence[Pairing], *, connection: PoolConnectionProxy
) -> None:
    await connection.copy_records_to_table(
        "pairings",
        records=[
            (pairing.round_id, pairing.board, pairing.white_id, pairing.black_id)
            for pairing in pairings
        ],
        columns=_PAIRING_COLUMNS,
    )
```
