---
paths:
  - "**/*.py"
---

# Naming

Every line of code names something, and no tool judges the meaning a name carries. Case, builtin
shadowing, single letters, length and the filler-word blacklist are the linters' job.

## General

- **Spell it out.** No abbreviations or jargon unless universally known (`url`, `id`, `http`,
  `json`, `sql`): `configuration`, not `cfg`; `response`, not `resp`.
- **The filler words the linter misses are the same idea one level up**: `manager`, `helper`,
  `util`, `misc`, `thing`, `tmp`. And the distinction it cannot make: a qualified compound is a
  real name — `pydantic` ships `FieldInfo`, where `Info` names the *description of* a field as
  opposed to the field itself. `info` alone would name nothing.
- **One concept — one word, everywhere.** `fetch` *or* `retrieve`, `remove` *or* `delete`,
  `customer` *or* `client` — never both.
- **Domain vocabulary**, not programmer words (`record`, `entry`, `node`), unless the domain is.

### Look at the Family Before You Name

Two existing names of the same shape for the same kind of job make that shape a rule: the third
must match it, and any outlier gets renamed. Checkable mechanically — group by signature and return
kind, then see whether the names share a shape; the shapes worth copying are in
`python-packaging`.

A codebase with twelve `duration_in(text)`-shaped names and three `find_duration`-shaped ones has
one concept and two vocabularies. Rename the three now: a library that waited renamed thirteen —
`isnot` to `is_not`, `notin_` to `not_in` — and still carries every old name as an alias.

## Functions and Methods

- **One name, one action.** Needing "and" to describe it (`validate_and_save_user`) means the
  function does two things — split it.
- **Commands are verbs; pure queries may be nouns; participles are banned.** A function that *does*
  something starts with a verb: `normalize_profile`, `send_invoice`. A side-effect-free query may
  be named after **what it returns** — `sqlalchemy`'s `Select.subquery()`, the stdlib's
  `math.hypot()`; a noun promises no side effect the way a verb promises one. **Never a past
  participle**: `matched(posting)`, `collapsed(text)`, `grouped(rows)` — the reader cannot tell a
  predicate from a builder. Write the one you mean: `is_matched` or `match_posting`. This is about
  **callables only**: a type alias or a variable may be a participle, because neither can be
  mistaken for an action — `Compared`, `Generated`, `discounted_price` all read as what they are.
- **The verb names the outcome, not the machinery.** `find_shortest_route`, not `run_dijkstra`.
  Implementation changes, intent does not.
- **A generic verb is a design signal, not a naming problem.** `process`, `handle`, `manage`, `do`
  say nothing because the unit does not know what it is for. When the only honest verb is generic,
  fix the responsibility and the name follows.
- **A hook is named for the event it receives** — a listener, a callback, anything the framework
  calls rather than you: `before_request`, `after_response`, `on_startup`. An override keeps the
  framework's name, generic verb or not: a transport's `handle_request`.
- **Shortest name that stays unambiguous in context.** Drop what the module, class or parameters
  already convey: `Order.total`, not `Order.order_total`; `Session.commit()`, not
  `commit_session()`. **The signature completes the sentence**: `find_user(email)`, not
  `find_user_by_email_string`. Use `by_` / `from_` / `to_` only to disambiguate siblings.
- **Predicates read as yes/no questions**: `is_`, `has_`, `can_`, `should_`, `in_` — `is_active`,
  `has_identity`, `in_transaction`. Never negate in the name: `is_valid`, not `is_invalid`, or
  callers write `not is_invalid` and readers stumble.
- **Distinguish query from command.** `get_`/`find_`/`compute_`/`is_` are side-effect free;
  `save_`, `update_`, `delete_`, `send_`, `publish_` announce a side effect. Never hide a write
  behind a `get_`.
- **The verb encodes cost, the return type the failure mode.** `fetch_`/`load_` imply I/O; `get_`
  a cheap local lookup; `compute_` CPU work. Absence that is normal is `-> User | None`, which the
  checker makes every caller handle; absence that is a bug raises behind `-> User`. A prefix scheme
  repeating what the annotation already states is a second source of truth, and drifts.
- **Conversions read as `to_` / `from_` / `as_`**; classmethod constructors are `from_…`.
- **Async functions are not renamed** — `async def` is visible and the checker enforces `await`.
- **Private helpers are still full names**: `_normalize_header`, not `_helper` / `_impl`.

```python
# WRONG — generic verb, hidden side effect, negated predicate, machinery, participle
def process_user_profile(profile: UserProfile) -> UserProfile: ...
def fetch_report(report_id: ReportId) -> Report: ...      # also writes to the audit log
def is_not_ready(job: Job) -> bool: ...
def run_levenshtein(left: str, right: str) -> int: ...
def matched(order: Order) -> MatchedFields: ...

# CORRECT
def normalize_user_profile(profile: UserProfile) -> UserProfile: ...
def fetch_report(report_id: ReportId) -> Report: ...
def record_report_access(report_id: ReportId, user_id: UserId) -> None: ...
def is_ready(job: Job) -> bool: ...
def edit_distance(left: str, right: str) -> int: ...    # pure query: a noun naming the result
def match_order(order: Order) -> MatchedFields: ...     # a verb, not a participle
```

## Variables and Parameters

- **Nouns for values, plural for collections**: `user`, `users`. Never `user_list` — the annotation
  already carries the container. **Collections name their elements**: `pending_orders`, not
  `order_queue`; `price_by_sku` for a dict keyed by SKU, where the `x_by_y` shape makes the key
  explicit. Loop variables are the singular: `for order in orders`.
- **Booleans read as predicates**, positive: `is_active`, `has_permission`, `should_refresh`.
  Never `flag`, `status`, `ok`.
- **Quantities carry their unit** — in every kind of name, not only locals: `timeout_seconds`,
  `file_size_bytes`, `price_usd`, and equally `MAX_UPLOAD_BYTES`, `CACHE_TTL_SECONDS`,
  `def wait(duration_seconds: float)`. Never a bare `timeout`, `size` or `limit` when the unit is
  ambiguous. The reader of a call site has the name and nothing else, and a wrong unit is the one
  mistake that produces a plausible result. A `timedelta` carries its unit in the type and needs
  none in the name; so does a name that repeats a standard's — `timeout` in float seconds as the
  stdlib uses it, a cookie's `max_age`.
- **Intermediate results are named after what they are, not their stage**: `discounted_price`, not
  `result2`. **Optional values say so in the type, not the name**: `user: User | None`, never
  `maybe_user`. **Constants describe the meaning, not the number**: `MAX_LOGIN_ATTEMPTS: Final = 5`.
- **Parameters are part of the public API** — callers pass them by keyword, so they must read in
  isolation. **Name the role, not the type**: `recipient: str`, not `string`; `predicate:
  Callable[…]`, not `func`; `on_complete` for a callback. Do not repeat the function name:
  `resize(image, width, height)`. **Reserved-word clashes take a trailing underscore**, never a
  misspelling — `sqlalchemy` ships exactly this: `is_`, `in_`. `*args` / `**kwargs` are renamed
  when they carry meaning: `*paths: Path`, `**headers: str`.

## Classes and Types

- **A noun or noun phrase for the concept**, singular. Enums are singular nouns too, with members
  as states or kinds.
- **Name the responsibility.** A suffix earns its place when it names a real role —
  `AliasGenerator`, `Session`, `Connection`, `MetaData`. A suffix that names nothing does not help:
  `UserManager` says less than `UserRegistration`, `UserDirectory` or `SessionStore`.
- **A family shares the noun and varies the qualifier.** The stdlib's `ipaddress` is the model:
  `IPv4Address`, `IPv6Address`, `IPv4Network`, `IPv6Network` — the noun names the concept, the
  qualifier the one axis that varies.
- **Contracts, `Base` classes and their implementations are named as `python-contracts` says**:
  the contract for the capability, an implementation for what makes it concrete.
- **Subclasses extend the parent's name with the distinguishing feature**, reading as "adjective +
  parent": `Cache` → `LruCache`; `ValueError` → `InvalidCurrencyError`.
- **Dataclasses and models are named after the thing they describe**, not the fact that they hold
  data: `Address`, `Coordinates`, `SearchFilters`. Where a project distinguishes families by suffix
  — `OrderModel` for a table, `OrderSchema` for a boundary shape — it keeps one such scheme and
  applies it everywhere, never two.
- **Exceptions name the failure, not the location.** `sqlalchemy`'s hierarchy is the reference:
  `NoSuchColumnError`, `NoReferencedTableError`, `AmbiguousColumnError`, `CircularDependencyError`
  — each says what went wrong precisely enough to act on. **A package prefix is for libraries
  only**: `PydanticUserError` earns it in someone else's traceback; in an application every
  exception in the traceback is yours, and the prefix is noise. The package's root exception is the
  one name that carries it, in both (`errors.md`).
- **Methods drop the class name**: `Order.total()`. **Properties are nouns, methods are verbs** — a
  property that does I/O or heavy computation is a bug; make it a `fetch_…` / `compute_…` method.
- **Type aliases name the domain meaning**: `type Headers = dict[str, str]`. A structural type
  describing someone else's shape takes `-Like`: `os.PathLike`. A kind suffix carries the
  distinction between related aliases — `Color` is the class, `ColorTuple` the shape, `ColorInput`
  the set of accepted inputs. Prefer `NewType` over a bare alias when two values share
  a runtime type but must not be confused.
- **Type parameters and `TypeVar`s** are named in `python-types`: `T`, and `_T` below 3.12.

```python
# WRONG — a suffix that names nothing, a plural enum
class DataManager(ABC): ...
class OrderStatuses(Enum): ...

# CORRECT — the noun names the responsibility; an enum is the singular kind
class OrderArchive(ABC): ...
class OrderStatus(Enum): ...
```

## The Name Fixes the Abstraction Level

A generically named unit — `Notifier`, `save_entity`, `calculate_total` — holds only generic logic:
no branching on concrete types, channels, providers, tenants or environments. **The vocabulary
test**: from the name alone, predict which domain words may appear in the body; `slack`, `vip` or
`postgres` inside `save_entity` is a leak, and a lying name is worse than no name.

- **A special-case branch is a design signal, not a fix.** Make the variation data
  (`discount_rate`), an injected strategy or callable, or a separate implementation of the
  contract — and keep the concrete rule in exactly one concretely named place.
- **Never re-implement a sibling's responsibility.** `OrderValidator` calls `AddressValidator`; it
  does not contain address rules.
- **Never upgrade a name to hide a leak.** A `MultiChannelNotifier` that branches on the channel
  still branches — the branching is the problem.

```python
# WRONG — a VIP rule leaked into a generic calculation
def calculate_total(order: Order) -> Money:
    subtotal = sum((line.price * line.quantity for line in order.lines), start=Money.zero())
    if order.customer.tier == "vip":
        return subtotal * Decimal("0.9")
    return subtotal

# CORRECT — the variation is data; one concretely named place knows about tiers
def calculate_total(order: Order, *, discount_rate: Decimal) -> Money:
    subtotal = sum((line.price * line.quantity for line in order.lines), start=Money.zero())
    return subtotal * (1 - discount_rate)

def vip_discount_rate(customer: Customer) -> Decimal: ...
```

## Names Are Local

A name states what the thing **is or does**, never where it came from, who calls it, or what
happens to it next. A name costs more to fix than a comment, because it is part of the signature
and every call site spells it out.

**The relocation test, applied to a name.** Move the unit to another package and read its name with
the neighbours hidden. A name that stops making sense — or that names a neighbour — was carrying
context that was never its own.

Four kinds leak, and each becomes a lie on a predictable day:

- **The argument's history** — `merged`, `downloaded`, `validated`, `cleaned`. The work does not
  depend on it, and the first caller who passes something else makes the name wrong.
- **A place in this project** — `runs`, `data_dir`, `tmp`. These name one repository's layout. The
  role is `source`, `into`, `where`.
- **The caller or its intent** — `save_for_upload`, `parse_for_the_nightly_job`, `for_reporting`.
  What the result is used for is the caller's business; a second caller with another purpose
  breaks it.
- **A neighbour's identity** — the vendor, library, framework or sibling module that happens to sit
  on the other side today. A boundary schema named after the third-party service that first
  answered it keeps that name through two replacements of the service, and then documents a
  vendor nobody in the codebase still calls.

```python
# WRONG — the argument's history and a place in this project; the vendor answering; the caller
def archive_logs(merged: Path, runs: Path) -> Path: ...
class AcmeCrmCustomerSchema(BaseModel): ...
def parse_for_nightly_job(payload: bytes) -> Customer: ...

# CORRECT — the signature states the roles; each is named for what it describes or does
def archive_logs(source: Path, into: Path) -> Path: ...
class CustomerSchema(BaseModel): ...
def parse_customer(payload: bytes) -> Customer: ...
```

**The carve-out, and it is narrow.** An implementation *is* named for what makes it concrete —
`SlackNotifier`, `PostgresUserRepository`, `RedisTokenStore`. The vendor is the whole distinction
between it and its siblings behind the same contract. The test still applies: delete the contract,
and the name must still say which implementation this is.

## Naming Self-Check

Before finishing any piece of code, verify every new identifier:

- [ ] Could a new teammate say what it is without opening its definition?
- [ ] Is it a bare filler word, or a catch-all verb (`process`, `handle`, `do`)?
- [ ] For functions: a precise verb, exactly one action, honest about side effects and cost?
- [ ] For predicates: positive, and phrased as a question?
- [ ] For quantities: is the unit in the name? For collections: plural, named after its elements?
- [ ] For classes and types: a noun, and does any suffix name a real role? Is every contract named
      for its capability, and does every `Base` hand down real implementation?
- [ ] Does it match the shape of its family, or is it the outlier that should be renamed?
- [ ] Is the same concept called by the same word everywhere else?
- [ ] Does the body stay at the abstraction level the name promises, with every concrete rule in
      exactly one concretely named unit?
- [ ] Does it survive the relocation test — no history, place, caller or neighbour in it?
