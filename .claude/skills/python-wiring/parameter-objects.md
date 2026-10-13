# Parameter Objects

The composition root and resource lifetime are in `SKILL.md`.

### A cohesive group of values passed as one frozen object is encouraged

**Why:** `RetryPolicy(attempts, backoff, jitter)` is a concept the callee uses whole; the
configuration root is a namespace of unrelated groups. Three questions tell them apart: does the
callee use essentially every field; is the name a concept (`RetryPolicy`) rather than an origin
(`Settings`, `Config`, `Env`); could a test build it in one line from literals? Three yeses make a
value to pass; one no makes the configuration root wearing a smaller name.

### A dispatcher that forwards options forwards them typed

**Why:** a factory handing one option bundle to whichever builder it selected takes `**options:
Unpack[SomeOptions]`, a `TypedDict` naming every field, so a misspelt option is rejected at the call
site; what it cannot check is that the selected builder got every field it requires — that arrives
as a `TypeError` on the first call, so builders that share one signature are preferred.

**Example:**
```python
# WRONG — untyped options: a misspelt timeout_secs passes the checker and the builder swallows it
def build_notifier(kind: NotifierKind, **options: object) -> Notifier:
    return _BUILDER_BY_KIND[kind](**options)


# CORRECT — every option is named once, and the checker rejects a misspelt one at the call site
class NotifierOptions(TypedDict, total=False):
    sender: str
    timeout_seconds: float


def build_notifier(kind: NotifierKind, **options: Unpack[NotifierOptions]) -> Notifier:
    return _BUILDER_BY_KIND[kind](**options)
```
