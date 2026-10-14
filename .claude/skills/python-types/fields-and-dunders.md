# Fields and Dunders

### A field says what it holds: secrets out of `repr`, ids and timestamps out of equality

**Why:** the generated `repr` prints a secret into the first log line that formats the object, and
an `issued_at` in `__eq__` makes two copies of one credential unequal. A mutable or computed default
is `field(default_factory=...)`; validation and derived fields go in `__post_init__`, through
`object.__setattr__` when frozen; a modified copy comes from `dataclasses.replace()`.

**Example:**
```python
# WRONG — repr shows the token, and a re-issued copy compares unequal
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ArchiveCredential:
    observer_name: str
    access_token: str
    issued_at: datetime


# CORRECT — each field states where it may appear
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ArchiveCredential:
    observer_name: str
    access_token: str = field(repr=False)
    issued_at: datetime = field(compare=False)
```

### A dunder is written where the behaviour fits, and `__eq__` comes with `__hash__`

**Why:** a class that defines `__eq__` alone gets `__hash__ = None`, and its first use as a set
member or a dict key raises `TypeError: unhashable type`. Value objects get both from
`@dataclass(frozen=True)`; an entity compares by identity and says so in both. A domain class that
is not a dataclass has a `__repr__` naming its identity and no secret; a container subclasses its
`collections.abc` ABC.

**Example:**
```python
# WRONG — equality without a hash: {telescope} raises TypeError
@final
class Telescope:
    def __init__(self, *, telescope_id: TelescopeId, site: str) -> None:
        self.telescope_id = telescope_id
        self.site = site

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Telescope) and other.telescope_id == self.telescope_id


# CORRECT — the entity's identity decides both equality and the hash
@final
class Telescope:
    def __init__(self, *, telescope_id: TelescopeId, site: str) -> None:
        self.telescope_id = telescope_id
        self.site = site

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Telescope) and other.telescope_id == self.telescope_id

    @override
    def __hash__(self) -> int:
        return hash(self.telescope_id)
```
