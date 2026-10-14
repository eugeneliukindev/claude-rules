---
paths:
  - "**/*.py"
---

# Python — Comments and Docstrings

Which names need a docstring is the linter's decision; what goes inside one, and whether a comment
is written at all, is not.

### A comment is one line, in one of four forms

**Why:** anything else restates the code, and a restatement goes stale the first time the code
changes. The four forms: a **caption** ending in a colon, indexing the lines below; a **reason** —
why *this* value, never what the line does; a **`TODO`** naming the condition that removes it; a
**`NOTE`** for a coupling the code cannot express. A paragraph is earned only by enumerated cases,
a rejected alternative or an honest limitation.

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

### Commented-out code, banners, stamps and change logs are deleted

**Why:** version control keeps all of them better; in the file they are noise that ages, and a name
explained in a comment is a name to fix instead.

### A comment describes only its own block; a docstring only the contract it is attached to

**Why:** a caller, a collaborator or an ordering named in prose — `# called by issue_invoice()`,
`"""Run by the nightly job."""`, "see the base class" — rots the moment the other side changes. The
relocation test: paste the block into another module — a comment that becomes wrong was leaking.
**Except:** the `NOTE:` above, for a coupling between artefacts that cannot import each other.
