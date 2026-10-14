# Downloads

Streaming instead of materializing is `python-performance`; the response class that sends a
generator, and where a framework runs a sync generator, are in `python-fastapi`.

### An export from a large table pages by key in short reads

**Why:** one cursor held open while a slow client downloads holds a transaction and a pooled
connection for as long as the client takes; pages by key release both between pages. A server-side
cursor is acceptable only under the stream's deadline, on a pool of its own.

**Example:**
```python
# WRONG — one cursor for the whole download, at the client's pace
async def export_hammer_sales(*, sales: HammerSaleArchive) -> AsyncGenerator[HammerSale]:
    async with sales.cursor() as cursor:
        async for sale in cursor:
            yield sale


# CORRECT — each page is a short read; nothing is held while the client downloads
async def export_hammer_sales(
    *, sales: HammerSaleArchive, sales_per_page: int = _SALES_PER_PAGE
) -> AsyncGenerator[HammerSale]:
    after_sale_id = 0
    while True:
        page = await sales.page_after(after_sale_id, limit=sales_per_page)
        if not page:
            return
        for sale in page:
            yield sale
        after_sale_id = page[-1].sale_id
```
