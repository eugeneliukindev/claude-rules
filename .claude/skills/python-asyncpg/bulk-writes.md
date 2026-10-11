# Bulk Writes

### Many plain rows go through `copy_records_to_table`; rows that need SQL, `executemany`

**Why:** a loop of `execute` is a round trip per row. `copy_records_to_table` is `COPY`, far faster
than inserts, inside the unit of work's transaction when it must be all or nothing; it cannot
upsert or return rows, and asyncpg quotes the table and column names itself. `executemany` fits a
row that needs `ON CONFLICT`, an expression or a lookup: one prepared statement, the rows pipelined,
and atomic since 0.22 — a failing row leaves none of the others.

**Example:**
```python
# WRONG — one round trip per track: ten thousand tracks are ten thousand statements
async def add_tracks(connection: PoolConnectionProxy, tracks: Sequence[PlaylistTrack]) -> None:
    for track in tracks:
        await connection.execute(
            _INSERT_PLAYLIST_TRACK, track.playlist_id, track.track_id, track.position
        )


# CORRECT — one COPY streams every track
async def add_tracks(connection: PoolConnectionProxy, tracks: Sequence[PlaylistTrack]) -> None:
    await connection.copy_records_to_table(
        "playlist_tracks",
        records=[(track.playlist_id, track.track_id, track.position) for track in tracks],
        columns=_PLAYLIST_TRACK_COLUMNS,
    )
```
