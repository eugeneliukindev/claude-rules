# FastAPI and FastStream

The seam between `python-fastapi` and `python-faststream`, linked from both skills.

### A route never publishes to the broker; the service writes an outbox row in its transaction

**Why:** a publish from the route either goes out before the commit — and the message describes a
change that a failed commit then never makes — or after it, and a crash in between loses the
message for a change that was made. The service writes the event as an outbox row in the same
transaction as the change, and a relay publishes what committed.

**Example:**
```python
# WRONG — the message leaves before the change commits, and a rollback cannot recall it
@adoptions_router.post("/adoptions/{adoption_id}/approve")
async def approve_adoption(
    adoption_id: AdoptionId, approval: ApprovalRequest, shelter: ShelterDep, broker: BrokerDep
) -> AdoptionResponse:
    await broker.publish({"adoption_id": str(adoption_id)}, "adoptions.approved")
    adoption = await shelter.approve(adoption_id, volunteer_id=approval.volunteer_id)
    return AdoptionResponse.from_domain(adoption)


# CORRECT — the service writes the event with the change; the relay publishes what committed
@adoptions_router.post("/adoptions/{adoption_id}/approve")
async def approve_adoption(
    adoption_id: AdoptionId, approval: ApprovalRequest, shelter: ShelterDep
) -> AdoptionResponse:
    adoption = await shelter.approve(adoption_id, volunteer_id=approval.volunteer_id)
    return AdoptionResponse.from_domain(adoption)
```
