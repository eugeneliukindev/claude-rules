# The CLI and the App's Lifespan

### Under `faststream run`, a `--factory` builds the app and its `lifespan` opens the resources

**Why:** `faststream run module:app` wants a module-level `app`, which pulls the broker and its
resources back to import time. `--factory` names a function that builds the app instead, and the
resources open in the app's `lifespan`, which wraps startup, the run and shutdown. `on_startup`
hooks run before the broker connects and `after_startup` hooks after the subscribers are already
consuming — neither is where a resource is built and handed out through `context`.

**Example:**
```python
# WRONG — the resource is built in a hook and handed out through FastStream's context
broker = RabbitBroker(WorkerSettings().amqp_url)
app = FastStream(broker)


@app.on_startup
async def _open_inventory(context: ContextRepo) -> None:
    context.set_global("inventory", HttpRoomInventory(open_http_client()))


# CORRECT — `faststream run bookings.worker:build_app --factory`; the lifespan owns the session
def build_app() -> FastStream:
    settings = WorkerSettings()
    broker = RabbitBroker(settings.amqp_url, graceful_timeout=_GRACEFUL_TIMEOUT_SECONDS)

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        async with managed_inventory_session(settings.inventory_url) as session:
            broker.include_router(build_booking_router(inventory=HttpRoomInventory(session)))
            yield

    return FastStream(broker, lifespan=lifespan)
```
