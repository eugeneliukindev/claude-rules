# The Entry Point and the App's Lifespan

### The entry point builds the settings and runs the app; the app's `lifespan` opens the resources

**Why:** `faststream run module:app` wants a module-level `app`, which pulls the broker and its
resources back to import time, and `--factory` calls a function with no arguments, which would have
to read the environment itself. The entry point builds the settings, builds the app from them and
runs it. `FastStream.run()` enters the `lifespan` first, starts the broker inside it, and leaves it
after the broker has stopped, so a resource opened there outlives every handler. `on_startup` hooks
run before the broker connects and `after_startup` hooks after the subscribers are already
consuming — neither is where a resource is built and handed out through `context`.

**Example:**
```python
# WRONG — the resource is built in a hook and handed out through FastStream's context
broker = RabbitBroker(TelemetrySettings().amqp_url)
app = FastStream(broker)


@app.on_startup
async def _open_scheduler(context: ContextRepo) -> None:
    context.set_global("scheduler", HttpInspectionScheduler(base_url=_MAINTENANCE_URL))


# CORRECT — the entry point reads the settings and unpacks them; the lifespan opens the resources
def build_telemetry_app(
    *,
    amqp_url: str,
    maintenance_url: str,
    graceful_timeout_seconds: float = _GRACEFUL_TIMEOUT_SECONDS,
) -> FastStream:
    broker = RabbitBroker(amqp_url, graceful_timeout=graceful_timeout_seconds)

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        async with open_inspection_scheduler(maintenance_url) as scheduler:
            broker.include_router(build_telemetry_router(scheduler=scheduler))
            yield

    return FastStream(broker, lifespan=lifespan)


def main() -> None:
    settings = TelemetrySettings()
    app = build_telemetry_app(
        amqp_url=settings.amqp_url, maintenance_url=settings.maintenance_url
    )
    asyncio.run(app.run())
```
