# Evaluation

### A rule earns its place by something the model would not do unprompted

**Why:** general practice the model already follows — `pathlib` over `os.path`, a large body
streamed instead of built — costs tokens in every session that loads it and dilutes the rules beside
it. What earns a place is a measured fact, a library's trap, a decision this project made, or the
correction of a default the model gets wrong; and a rule homed elsewhere is not written twice.
Anthropic's guidance asks it of every paragraph: does it justify its token cost?

**Example:**
```markdown
<!-- WRONG — what the model already does -->
### Paths are built with `pathlib`, not string concatenation

<!-- CORRECT — a trap the model does not know -->
### `uvx pip-audit` audits its own environment; the lock's export is what gets audited
```

### A rule is tested with a realistic task that never mentions it, without the rule first

**Why:** a rule is a hypothesis that the model behaves differently with it than without it. Run the
task in a fresh session without the rule and then with it, a few times each, and read the produced
code against the rule; a rule whose task passes without it restates the default and is deleted.
Path-scoped rules arrive on a read, so the task is seeded with a file to read, and its prompt holds
no request that outranks the rule — "make sure it is well documented" overrides any rule about
comments, by design.

**Example:**
```text
# WRONG — the prompt names the rule, so the run measures obedience, not the rule
Write the cache for profile lookups, and remember to add jitter to the TTL.

# CORRECT — a task the rule should shape, with a file to read first
Read src/profiles/service.py, then add a cache in front of ProfileLookup.fetch.
```
