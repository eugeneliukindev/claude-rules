# FastAPI and FastStream

The seam between `python-fastapi` and `python-faststream`, linked from both skills. The outbox is
`python-persistence`.

### A route never publishes to the broker; the service writes an outbox row in its transaction

**Why:** a publish from the route either goes out before the commit — and the message describes a
change that a failed commit then never makes — or after it, and a crash in between loses the
message for a change that was made. The service writes the event as an outbox row in the same
transaction as the change, and a relay publishes it.

**Example:**
```python
# WRONG — the message leaves before the change commits, and a rollback cannot recall it
@tasks_router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: TaskId, assignee: AssigneeRequest, tasks: TaskServiceDep, broker: BrokerDep
) -> TaskResponse:
    await broker.publish({"task_id": str(task_id)}, "tasks.assigned")
    return TaskResponse.from_domain(await tasks.assign(task_id, assignee.user_id))


# CORRECT — the service writes the event with the change; the relay publishes what committed
@tasks_router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: TaskId, assignee: AssigneeRequest, tasks: TaskServiceDep
) -> TaskResponse:
    return TaskResponse.from_domain(await tasks.assign(task_id, assignee.user_id))
```
