# Naming Contracts and Implementations

How a contract is declared and what its methods look like are in `SKILL.md`.

## Contents

- A contract is named after the capability, without a prefix or a mechanism suffix
- `Base` means "inherit me", never "implement me"
- An implementation is named for what makes it concrete, never `Default` or `Impl`

### A contract is named after the capability, without a prefix or a mechanism suffix

**Why:** `Notifier`, `UserDirectory`, `Comparable` — an agent noun or an "-able" adjective says what
the thing does; `…Protocol`, `…Interface` and `…ABC` say how it was declared, which no caller cares
about. The implementations carry the qualifier that distinguishes them: `EmailNotifier`,
`LdapUserDirectory`. Stdlib ABCs keep their stdlib names.

**Example:**
```python
# WRONG — the mechanism as the name, and Base on a class that hands nothing down
class UserDirectoryProtocol(Protocol):
    def find(self, email: str) -> User | None: ...


class BaseUserDirectory(ABC):
    @abstractmethod
    def find(self, email: str) -> User | None: ...


# CORRECT — the contract names the capability; the implementation names what makes it concrete
class UserDirectory(ABC):
    @abstractmethod
    def find(self, email: str) -> User | None: ...


@final
class LdapUserDirectory(UserDirectory):
    def __init__(self, *, connection: LdapConnection) -> None:
        self._connection = connection

    @override
    def find(self, email: str) -> User | None:
        entry = self._connection.search_one(f"(mail={email})")
        return None if entry is None else User(user_id=UserId(entry.uid), email=email)
```

### `Base` means "inherit me", never "implement me"

**Why:** the prefix is earned by a class that carries shared *implementation* down — fields,
defaults, ready methods — as `BaseHTTPRequestHandler` and `BaseException` do; a contract hands
nothing down. The test is mechanical: delete the base and see what the subclasses lose — fields or
working methods make it a `Base`, only a promise the checker was already making makes it a
contract. A shared base only its own module inherits is private: `_BaseCookie`.

### An implementation is named for what makes it concrete, never `Default` or `Impl`

**Why:** `DefaultNotifier` and `NotifierImpl` say nothing; the driver, the transport or the storage
does. If nothing distinguishes the implementation, there was no contract worth writing.
