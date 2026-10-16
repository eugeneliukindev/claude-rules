---
paths:
  - "**/*.py"
---

# Naming

No tool judges the meaning a name carries.

## Words

### One concept has one word everywhere, and a name matches the shape of its family

**Why:** `fetch` *and* `retrieve`, `patient` *and* `client` in one codebase make the reader wonder
whether they differ; two names of one shape for one kind of job make the shape a rule, the third
matches, and an outlier is renamed now - a library that waited still carries every old name as an
alias.

### A collection is a plural named for its elements; a mapping reads `x_by_y`

**Why:** `invoice_list` repeats the annotation and `invoice_queue` names the container -
`pending_invoices` says what is in it, and `rate_by_currency` says the key as well.

### A quantity carries its unit in the name

**Why:** a wrong unit is the one mistake that produces a plausible result - `timeout_seconds`,
`MAX_UPLOAD_BYTES`, `price_usd`.
**Except:** a `timedelta` carries its unit in the type; a name that repeats a standard's - `timeout`
in float seconds as the stdlib uses it - needs none.

### The prefix tells the cost and the side effect; the return type tells the failure

**Why:** `get_` is a cheap lookup, `find_` a search that may find nothing, `fetch_` and
`load_` do I/O, `compute_` is CPU work, `save_`, `send_`, `publish_` write - never I/O behind a
`get_` or a property. A query has no side effect; a command returns `None` or what its effect
assigned. A generic verb - `process`, `handle` - means the unit does not know what it is for.
**Except:** a method of a store contract keeps its family's verbs - a repository's `get` raises when
the row is missing and its `find` returns `None`; a cache's `get` returns `None` on a miss.

### Two ids of one runtime type are each a `NewType`

**Why:** two ids that are both `str` are swapped silently at a call site, and it type-checks; a
`type` alias names what a shape means, `type Headers = dict[str, str]`.

## The Name Fixes the Abstraction Level

### A generically named unit holds only generic logic

**Why:** from the name alone a reader predicts which domain words may appear in the body - `slack`,
`vip` or `postgres` inside `calculate_total` is a leak. The variation becomes data, an injected
strategy or a separate implementation, and the concrete rule lives in one concretely named place; a
name is never upgraded to hide a leak - a `MultiChannelNotifier` that branches on the channel still
branches.

## Names Are Local

### A name says what the thing is or does - never its history, place, caller or neighbour

**Why:** every call site spells the name out. Read it moved to another package - the argument's
history (`merged`) turns false for the next caller; a place (`data_dir`) names one repository's
layout; the caller (`for_nightly_job`) breaks for a second; a vendor in a schema's name outlives
the vendor.
**Except:** an implementation *is* named for what makes it concrete - `SlackNotifier`,
`PostgresUserRepository`.

**Example:**
```python
# WRONG - the argument's history, a place in this project, the caller, the vendor
def archive_statements(merged: Path, runs: Path) -> Path:
    return Path(shutil.make_archive(str(runs / merged.stem), "zip", merged))


def parse_for_nightly_job(payload: bytes) -> Customer:
    return AcmeCrmCustomerSchema.from_json(payload).to_domain()


# CORRECT - the signature states the roles; each name says what it describes or does
def archive_statements(source: Path, *, into: Path) -> Path:
    return Path(shutil.make_archive(str(into / source.stem), "zip", source))


def parse_customer(payload: bytes) -> Customer:
    return CustomerSchema.from_json(payload).to_domain()
```
