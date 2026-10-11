# The Same Rules in Each Library

What `SKILL.md` asks of every consumer, and where each library keeps it. FastStream's mechanics are
in `python-faststream`. Celery ships without type information: under `mypy --strict` every task and
signal handler is an `untyped-decorator` error until the `celery-types` stubs are a dev dependency.

| | ack after the work | bounded attempts | dead letters | handler deadline | in flight |
|---|---|---|---|---|---|
| FastStream on RabbitMQ (`python-faststream`) | `AckPolicy.REJECT_ON_ERROR` | queue's `x-delivery-limit` | queue's `x-dead-letter-exchange` | `asyncio.timeout` | `Channel(prefetch_count=…)`; none by default |
| Celery | `acks_late=True` and `task_reject_on_worker_lost=True`; the default acks before running | `max_retries` (3) | none built in: a failed task is acked | `soft_time_limit`, `time_limit` | `worker_prefetch_multiplier` × concurrency (4) |
| taskiq | `--ack-type` `when_saved` (default) or `when_executed` | `SmartRetryMiddleware(default_retry_count=…)` | none built in | `timeout` label | `--max-async-tasks` (100) |
| aiokafka | `enable_auto_commit=False`, `commit()` after; the default commits every 5 s whatever happened | your own counter | a dead-letter topic | `asyncio.timeout` | `max_poll_records`; none by default |
| arq | — | `max_tries` (5) | none built in | `job_timeout` (300 s) | `max_jobs` (10) |

### A library's acknowledge-on-receipt default is switched off where the consumer is configured

**Why:** Celery acks before running a task, and aiokafka commits every five seconds whatever
happened; under either, a crash after the ack loses the message the handler never finished. The
row above names the switch for each library.

**Example:**
```python
# WRONG — Celery's default: the task is acknowledged before it runs
celery_app = Celery("bookings")


@celery_app.task
def confirm_booking_task(body: str) -> None:
    asyncio.run(on_booking_confirmed(body.encode(), inventory=_resources.inventory))


# CORRECT — acknowledged after the task returns, and redelivered if its worker dies
celery_app = Celery("bookings")
celery_app.conf.update(task_acks_late=True, task_reject_on_worker_lost=True)


@celery_app.task
def confirm_booking_task(body: str) -> None:
    asyncio.run(on_booking_confirmed(body.encode(), inventory=_resources.inventory))
```
