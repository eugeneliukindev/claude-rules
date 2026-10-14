# Naming Contracts and Implementations

How a contract is declared and what its methods look like are in `SKILL.md`.

## Contents

- A contract is named after the capability, an implementation for what makes it concrete, and neither for its mechanism
- `Base` means "inherit me", never "implement me"

### A contract is named after the capability, an implementation for what makes it concrete, and neither for its mechanism

**Why:** `TranslationEngine`, `TranslatorDirectory`, `Comparable` — an agent noun or an "-able"
adjective says what the thing does; `…Protocol`, `…Interface` and `…ABC` say how it was declared,
which no caller cares about, and `DefaultTranslationEngine` or `TranslationEngineImpl` says
nothing. The implementations carry the qualifier that distinguishes them — the driver, the
transport or the storage: `DeepLTranslationEngine`, `LdapTranslatorDirectory`. If nothing
distinguishes an implementation, there was no contract worth writing. Stdlib ABCs keep their
stdlib names.

**Example:**
```python
# WRONG — the mechanism as the name, and Base on a class that hands nothing down
class TranslatorDirectoryProtocol(Protocol):
    def find(self, email: str) -> Translator | None: ...


class BaseTranslatorDirectory(ABC):
    @abstractmethod
    def find(self, email: str) -> Translator | None: ...


# CORRECT — the contract names the capability; the implementation names what makes it concrete
class TranslatorDirectory(ABC):
    @abstractmethod
    def find(self, email: str) -> Translator | None: ...


@final
class LdapTranslatorDirectory(TranslatorDirectory):
    def __init__(self, *, connection: LdapConnection) -> None:
        self._connection = connection

    @override
    def find(self, email: str) -> Translator | None:
        entry = self._connection.search_one(f"(mail={email})")
        if entry is None:
            return None
        return Translator(translator_id=TranslatorId(entry.uid), email=email)
```

### `Base` means "inherit me", never "implement me"

**Why:** the prefix is earned by a class that carries shared *implementation* down — fields,
defaults, ready methods — as `BaseHTTPRequestHandler` and `BaseException` do; a contract hands
nothing down. The test is mechanical: delete the base and see what the subclasses lose — fields or
working methods make it a `Base`, only a promise the checker was already making makes it a
contract. A shared base only its own module inherits is private: `_BaseCookie`.
