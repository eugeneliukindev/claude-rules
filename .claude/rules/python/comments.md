---
paths:
  - "**/*.py"
---

# Python — Comments and Docstrings

Which names need a docstring is the linter's decision; what goes inside one, and whether a comment
is written at all, is not. A legal header is exempt; where a suppression's reason goes is in
`core.md`.

## Comments

### A comment is one line, in one of four forms

**Why:** anything else restates the code, and a restatement goes stale the first time the code
changes. The four forms: a **caption** ending in a colon, indexing the lines below; a **reason** —
why *this* value, never what the line does, with a ticket link beside it, never instead of it; a
**`TODO`** naming the condition that removes it, never an owner; a **`NOTE`** for a coupling the
code cannot express, kept for what crosses languages once a shared constant would do the rest.

**Example:**
```python
# WRONG — a narration of what each line does
# set the timeout
_IDLE_TIMEOUT_SECONDS: Final = 30
# loop over the devices and push to each one
for device in devices:
    push(device, alert)


# CORRECT — a caption, a reason, a TODO with its condition, a NOTE across languages
# Limits the push gateway imposes:
_IDLE_TIMEOUT_SECONDS: Final = 30  # the gateway drops idle connections at 35
_MAX_DEVICES_PER_BATCH: Final = 500  # larger batches are rejected with a 413
# TODO: drop the fallback once the legacy gateway is switched off
# NOTE: mirrored in push_limits.swift, which cannot import this module
```

### A paragraph is earned by enumerated cases, a rejected alternative, or an honest limitation

**Why:** those three are what the code cannot show — the cases a reader cannot recover from it, the
alternative that was tried and why it loses here, a limit recorded as "not supported for now";
everything else fits in one line or in a better name.

### Commented-out code, banners, stamps and change logs are deleted

**Why:** version control keeps all of them better; in the file they are noise that ages, and a name
explained in a comment is a name to fix instead. A published docstring's version note is not a
change log.

## Docstrings

### A docstring's length follows publication, not complexity

**Why:** where a generator renders it for outside readers it is full — summary, parameters, return
value, the errors the function's own logic raises; everywhere else it is one line and often absent
(one reference library documents 97% of its exported names and 17% of its private functions). It
states the contract, not the algorithm.

## Comments and Docstrings Are Local

### A comment describes only its own block; a docstring only the contract it is attached to

**Why:** both must stay true when anything outside changes. A caller, a collaborator or an ordering
named in prose — `# called by issue_invoice()`, `"""Run by the nightly job."""` — rots the moment
the other side changes, and nothing checks it; "as described above" or "see the base class" breaks
the same way, so an override either adds nothing and has no docstring or states its contract in
full. The test: paste the block into another module — a comment that becomes wrong was leaking, and
one that can only be written by referring elsewhere means the design is wrong.
**Except:** the `NOTE:` above, for a coupling between artefacts that cannot import each other.

**Example:**
```python
# WRONG — a caller and an ordering in prose, and a comment restating the check
def validate_invoice(invoice: Invoice) -> None:
    # called by issue_invoice() before _persist(); do not reorder
    # check the invoice does not have too many lines
    if len(invoice.lines) > 100:
        raise InvoiceTooLongError(invoice.number)


# CORRECT — the number is named, and one line says why this value
_MAX_INVOICE_LINES: Final = 100  # the e-invoicing network rejects longer documents


def validate_invoice(invoice: Invoice) -> None:
    if len(invoice.lines) > _MAX_INVOICE_LINES:
        raise InvoiceTooLongError(invoice.number)
```
