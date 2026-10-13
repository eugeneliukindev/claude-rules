# Where a Contract and Its Implementations Live

How a contract is declared and what its methods look like are in `SKILL.md`.

## Contents

- A contract and its implementations are one directory, and nothing else is
- `base.py` is a position, not a `Base` class
- The contract's module imports nothing any implementation needs
- A helper only one implementation uses is private and stays in the group
- No contract, no directory

### A contract and its implementations are one directory, and nothing else is

**Why:** the contract is the reason the implementations exist; one directory per capability, the
contract in `base.py`, one module per implementation named for what makes it concrete, and an
`__init__.py` exporting the contract and the implementations — so a new implementation is a new
file and no existing file changes.
**Except:** an implementation whose driver is an optional extra is reached through its builder, so
importing the contract never imports the driver (the per-extra facade in `python-packaging`).

### `base.py` is a position, not a `Base` class

**Why:** the module sits at the base of the group; the class inside it is still named for the
capability — `Notifier`, never `BaseNotifier`. One rule is about a file, the other about a class.

### The contract's module imports nothing any implementation needs

**Why:** an import of a driver in `base.py` silently makes every consumer of the contract depend on
that driver, and the split stops paying.

**Example:**
```python
# WRONG — notifications/base.py imports the SDK one implementation uses
from slack_sdk import WebClient


class Notifier(ABC):
    @abstractmethod
    def send(self, recipient: UserId, message: Message) -> None: ...


# CORRECT — notifications/slack.py is the only file that knows the SDK exists
from slack_sdk import WebClient

from notifications.base import Notifier


@final
class SlackNotifier(Notifier):
    def __init__(self, *, client: WebClient, channel: str) -> None:
        self._client = client
        self._channel = channel

    @override
    def send(self, recipient: UserId, message: Message) -> None:
        self._client.chat_postMessage(channel=self._channel, text=f"<@{recipient}> {message}")
```

### A helper only one implementation uses is private and stays in the group

**Why:** `_templates.py` beside `smtp.py` is found by whoever edits `smtp.py`; the same code in a
shared `utils` is found by nobody and imported by everybody.

### No contract, no directory

**Why:** an implementation that will only ever be the only one is a single module named concretely,
with no `base.py` above it; the group appears when the second implementation does, or when a test
needs a fake — the same threshold that earns the contract.
