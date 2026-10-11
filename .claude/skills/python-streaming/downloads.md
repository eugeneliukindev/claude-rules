# Downloads

Streaming instead of materializing is `python-performance`; the response class that sends a
generator, and where a framework runs a sync generator, are in `python-fastapi`.

### An export from a large table pages by key in short reads

**Why:** one cursor held open while a slow client downloads holds a transaction and a pooled
connection for as long as the client takes; pages by key release both between pages. A server-side
cursor is acceptable only under the stream's deadline, on a pool of its own.

**Example:**
```python
# WRONG — one unit of work for the whole download, at the client's pace
async def stream_entries(*, unit_of_work: UnitOfWork) -> AsyncIterator[AuditEntry]:
    async with unit_of_work:
        async for entry in unit_of_work.audit_entries.stream_all():
            yield entry


# CORRECT — each page is a short read; nothing is held while the client downloads
async def stream_entries(
    *, unit_of_work: Callable[[], UnitOfWork], page_size: int = _PAGE_SIZE
) -> AsyncIterator[AuditEntry]:
    after_id = 0
    while True:
        async with unit_of_work() as unit:
            page = await unit.audit_entries.page_after(after_id, limit=page_size)
        if not page:
            return
        for entry in page:
            yield entry
        after_id = page[-1].entry_id
```
