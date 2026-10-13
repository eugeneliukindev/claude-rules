# The CLI and the App's Lifespan

### The entry point builds the settings and runs the app; the app's `lifespan` opens the resources

**Why:** `faststream run module:app` wants a module-level `app`, which pulls the broker and its
resources back to import time, and `--factory` calls a function with no arguments, which would have
to read the environment itself. The entry point builds the settings, builds the app from them and
runs it; the resources open in the app's `lifespan`, which wraps startup, the run and shutdown.
`on_startup` hooks run before the broker connects and `after_startup` hooks after the subscribers
are already consuming — neither is where a resource is built and handed out through `context`.

**Example:**
```python
# WRONG — the resource is built in a hook and handed out through FastStream's context
broker = RabbitBroker(WorkerSettings().amqp_url)
app = FastStream(broker)


@app.on_startup
async def _open_inventory(context: ContextRepo) -> None:
    context.set_global("inventory", HttpRoomInventory(open_http_client()))


# CORRECT — the entry point reads the settings and unpacks them; the lifespan opens the resources
def build_app(
    *,
    amqp_url: str,
    inventory_url: str,
    graceful_timeout_seconds: float = _GRACEFUL_TIMEOUT_SECONDS,
) -> FastStream:
    broker = RabbitBroker(amqp_url, graceful_timeout=graceful_timeout_seconds)

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        async with managed_inventory_session(inventory_url) as session:
            broker.include_router(build_booking_router(inventory=HttpRoomInventory(session)))
            yield

    return FastStream(broker, lifespan=lifespan)


def main() -> None:
    settings = WorkerSettings()
    app = build_app(amqp_url=settings.amqp_url, inventory_url=settings.inventory_url)
    asyncio.run(app.run())
```
