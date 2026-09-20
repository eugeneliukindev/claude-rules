---
paths:
  - "**/*.py"
---

# Naming

Loads with `core.md`, because every line of code names something and no tool judges the meaning a
name carries. Case conventions, builtin shadowing, single letters, name length and the blacklist of
filler words are the linters' job and are not repeated here.

Examples are taken from `pydantic` and `sqlalchemy` — both large, long-lived, and named by people
who then had to live with the choice.

## General

- **Reveal intent.** A name answers three questions without a comment: what is it, why does it
  exist, how is it used. If a comment is needed to explain the name, the name is wrong.
- **Spell it out.** No abbreviations or jargon unless universally known (`url`, `id`, `http`,
  `json`, `sql`): `configuration`, not `cfg`; `response`, not `resp`.
- **The filler words the linter misses are the same idea one level up**: `manager`, `helper`,
  `util`, `misc`, `thing`, `tmp`. And the distinction it cannot make: a qualified compound is a
  real name — `pydantic` ships `FieldInfo`, where `Info` names the *description of* a field as
  opposed to the field itself. `info` alone would name nothing.
- **Length matches scope.** Three lines inside a comprehension may be short; a module-level or
  public name is fully explicit.
- **One concept — one word, everywhere.** `fetch` *or* `retrieve`, `remove` *or* `delete`,
  `customer` *or* `client` — never both.
- **Use domain vocabulary**, not generic programmer words (`record`, `entry`, `node`) unless the
  domain itself is generic. Pronounceable, searchable, no jokes or internal slang.

### Look at the Family Before You Name

Two existing names of the same shape for the same kind of job make that shape a rule: the third
must match it, and any outlier gets renamed. Checkable mechanically — group by signature and return
kind, then see whether the names share a shape. The shapes worth copying:

- **Namespace prefix** — `model_validate`, `model_dump`, `model_copy`, `model_json_schema`: every
  method of `BaseModel` is prefixed so a user's own field named `dump` can never collide.
- **Scope pair** — `field_validator` / `model_validator`: same job, two scopes, one suffix apart.
- **Input kind** — `validate_python`, `validate_json`, `validate_strings`: one verb, the suffix
  names what is accepted.
- **Position** — `BeforeValidator`, `AfterValidator`, `WrapValidator`: the adjective is the only
  variable.
- **Derive a copy** — `with_only_columns`, `with_hint`, `with_for_update`: `with_` returns a new
  object that also carries X.
- **Negated variant** — `correlate` / `correlate_except`, so both read the same way.
- **Symmetric pair** — `get_label_style` / `set_label_style`, differing by verb only.
- **Plurality** — `scalar` / `scalars`: singular returns one, plural returns many.
- **Opposites are symmetrical** — `open`/`close`, `add`/`remove`, `start`/`stop`,
  `serialize`/`deserialize`, `commit`/`rollback`.

A codebase with twelve `duration_in(text)`-shaped names and three `find_duration`-shaped ones has
one concept and two vocabularies. Rename the three.

## Functions and Methods

- **One name, one action.** Needing "and" to describe it (`validate_and_save_user`) means the
  function violates SRP — split it.
- **Commands are verbs; pure queries may be nouns; participles are banned.** A function that *does*
  something starts with a verb: `normalize_profile`, `send_invoice`. A side-effect-free query may
  be named after **what it returns** — `pydantic`'s `version_short()`, `sqlalchemy`'s
  `selected_columns`; a noun promises purity as reliably as a verb promises action. **Never a past
  participle**: `matched(posting)`, `collapsed(text)`, `grouped(rows)` — the reader cannot tell a
  predicate from a builder. Write the one you mean: `is_matched` or `match_posting`. Neither
  library has a name of this shape anywhere. This is about **callables only**: a type alias or a
  variable may be a participle, because neither can be mistaken for an action — `Compared`,
  `Generated`, `discounted_price` all read as what they are.
- **The verb names the outcome, not the machinery.** `find_shortest_route`, not `run_dijkstra`.
  Implementation changes, intent does not.
- **A generic verb is a design signal, not a naming problem.** `process`, `handle`, `manage`, `do`
  say nothing because the unit does not know what it is for. Neither library has a public
  `process_*`, `handle_*` or `manage_*`. When the only honest verb is generic, fix the
  responsibility and the name follows.
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
- **Encode cost and failure mode.** `fetch_`/`load_` imply I/O; `get_` a cheap local lookup;
  `compute_` CPU work. `find_x` returns `None` when missing, `get_x` raises — used consistently
  across the whole codebase.
- **Conversions read as `to_` / `from_` / `as_`**; classmethod constructors are `from_…`.
- **Async functions are not renamed** — `async def` is visible and the checker enforces `await`.
- **Private helpers are still full names**: `_normalize_header`, not `_helper` / `_impl`.

  ```python
  # WRONG — generic verb, hidden side effect, negated predicate, machinery, participle
  def process_user_data(payload: dict[str, str]) -> None: ...
  def get_report(report_id: int) -> Report: ...          # also writes to the audit log
  def is_not_ready(job: Job) -> bool: ...
  def run_levenshtein(left: str, right: str) -> int: ...
  def matched(order: Order) -> MatchedFields: ...

  # CORRECT
  def normalize_user_profile(profile: UserProfile) -> UserProfile: ...
  def fetch_report(report_id: int) -> Report: ...
  def record_report_access(report_id: int, user_id: int) -> None: ...
  def is_ready(job: Job) -> bool: ...
  def edit_distance(left: str, right: str) -> int: ...   # pure query — noun naming the result
  def match_order(order: Order) -> MatchedFields: ...    # command — verb
  def find_user(user_id: int) -> User | None: ...
  def get_user(user_id: int) -> User: ...                # raises UserNotFoundError
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
  mistake that produces a plausible result.
- **Intermediate results are named after what they are, not their stage**: `discounted_price`, not
  `result2`. **Optional values say so in the type, not the name**: `user: User | None`, never
  `maybe_user`. **Constants describe the meaning, not the number**: `MAX_LOGIN_ATTEMPTS = 5`.
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
- **A family shares the noun and varies the qualifier.** `pydantic`'s URL types are the model:
  `AnyUrl`, `HttpUrl`, `FileUrl`, `FtpUrl` — one noun, one axis of variation.
- **Describe what it is, not how it is built.** `TaskQueue`, not `RedisTaskQueue` — unless a second
  implementation exists and the distinction is the point.
- **A contract is named after the capability, without a prefix.** A contract base class — or, at a
  foreign boundary, a `Protocol` — is an agent noun or an "-able" adjective and nothing more:
  `Notifier`, `UserRepository`, `Comparable`. Never a mechanism suffix (`…Protocol`, `…Interface`,
  `…ABC`). The implementations carry the qualifier: `EmailNotifier`, `PostgresUserRepository`.
  Stdlib ABCs keep their stdlib names, and are never wrapped just to rename them.
  **The carve-out is a published extension point**: a shape a third party implements in their own
  code — `PydanticPluginProtocol` — where the mechanism is part of what the outsider must know,
  because it says "satisfy this, do not inherit it". Inside your own tree that distinction is
  already visible in the class line, and the suffix is noise.
- **`Base` means "inherit me", never "implement me".** The prefix is earned by a class that carries
  shared *implementation* down to its subclasses: fields, defaults, ready methods — that is what it
  means everywhere in the ecosystem, from `pydantic.BaseModel` to `sqlalchemy.DeclarativeBase`. A
  contract has nothing to hand down, so it has no `Base` to earn. The test is mechanical: delete
  the base and see what the subclasses lose. Lose fields or working methods — it is a `Base`. Lose
  only a promise the checker was already making — it is a contract, named for the capability.
- **A shared base that only its own module inherits is private**: `_BaseCookie`, `_BaseAuth`.
- **Where a contract and its single implementation would collide**, the implementation names what
  makes it concrete — its driver, its transport, its storage — never `Default` or `Impl`. If
  nothing distinguishes it, there was no contract worth writing.
- **Subclasses extend the parent's name with the distinguishing feature**, reading as "adjective +
  parent": `Cache` → `LruCache`; `ValueError` → `InvalidCurrencyError`.
- **Dataclasses and models are named after the thing they describe**, not the fact that they hold
  data: `Address`, `Coordinates`, `SearchFilters`. Where a project distinguishes families by suffix
  — `OrderModel` for a table, `OrderSchema` for a boundary shape — it keeps one such scheme and
  applies it everywhere, never two.
- **Exceptions name the failure, not the location.** `sqlalchemy`'s hierarchy is the reference:
  `NoSuchColumnError`, `NoReferencedTableError`, `AmbiguousColumnError`, `CircularDependencyError`
  — each says what went wrong precisely enough to act on. Never `CustomException`, `MyError`,
  `Failure`. **A package prefix on exceptions is for libraries only**: `PydanticUserError` earns it
  by surfacing in someone else's traceback next to `ValueError`. Inside an application, where every
  exception in the traceback is yours, the prefix is noise on every line.
- **Methods drop the class name**: `Order.total()`. **Properties are nouns, methods are verbs** — a
  property that does I/O or heavy computation is a bug; make it a `fetch_…` / `compute_…` method.
- **Type aliases name the domain meaning**: `type Headers = dict[str, str]`. A structural type
  describing someone else's shape takes `-Like`: `PathLike`, `_TypeVarLike`. A kind suffix carries the distinction
  between related aliases — `Color` is the class, `ColorTuple` the shape, `ColorType` the set of
  accepted inputs. Prefer `NewType` over a bare alias when two values share a runtime type but must
  not be confused.
- **Type parameters are single capital letters** — `T` by default, `K`/`V` for key/value, `P`/`R`
  for `ParamSpec`/return. The bound carries the meaning (`[T: BaseModel]`); the letter does not
  need to. Descriptive names are for the rare generic with three or more parameters.
  **Below Python 3.12 the same letters take the `_T` shape**: a `TypeVar` is a module-level name,
  so it is private and suffixed — `_T`, `_KT`, `_VT`, `_P`, `_R`. Where one module declares several
  and the letters stop telling them apart, the role goes in front of the suffix, never instead of
  it: `_BackendT`, `_ModelT`. A variance marker goes after it — `_ModelTCo` for the covariant
  twin — so the two sort together and read as a pair. One shape per codebase, decided by the
  version floor, never both.

  ```python
  # 3.12+ — the parameter belongs to the class, so it needs no module-level name
  class Repository[T: Entity](ABC): ...

  # 3.11 and below — a module-level TypeVar: private, suffixed, bound doing the work
  _T = TypeVar('_T', bound=Entity)
  _BackendT = TypeVar('_BackendT', bound=SyncBackend | AsyncBackend)

  class Repository(ABC, Generic[_T]): ...
  ```

  ```python
  # WRONG — Base on a contract, Base on a leaf, a suffix that names nothing, plural enum
  class BaseUserDirectory(ABC): ...           # nothing to inherit: it hands down no implementation
  class BaseLdapUserDirectory: ...            # a leaf, and what makes it concrete is what matters
  class UserDirectoryProtocol(Protocol): ...  # the mechanism is not the name
  class DataManager(ABC): ...
  class OrderStatuses(Enum): ...

  # CORRECT — the contract names the capability, the implementations name what makes them concrete
  class UserDirectory(ABC):
      @abstractmethod
      def find(self, email: str) -> User | None: ...

  class LdapUserDirectory(UserDirectory): ...
  class InMemoryUserDirectory(UserDirectory): ...
  class UserNotFoundError(LookupError): ...
  ```

## The Name Fixes the Abstraction Level

A name fixes the abstraction level of a function or class; the body **MUST** stay at that level.
Logic "leaks" when a generically named thing starts knowing about specific cases, or when a
specifically named thing takes over a sibling's responsibility. Both make the name lie, and a lying
name is worse than no name.

- **Generic name → only generic logic.** `Notifier`, `save_entity`, `TaskQueue` contain **no**
  branching on concrete types, channels, providers, tenants or environments.
- **Concrete logic lives in a concretely named unit, and in exactly one.** Anything Slack-only goes
  in `SlackNotifier`; anything VIP-only in `VipDiscountPolicy`.
- **A "special case" branch in a generic body is a design signal, not a fix.** When a generic unit
  needs "but for X do it differently", do one of these and never add the branch: extract
  `XSomething` as a separate implementation of the same contract; move the variation into an
  injected strategy or callable; or, if the variation is data, pass it as data (`discount_rate`).
- **Never re-implement a sibling's responsibility.** `OrderValidator` calls `AddressValidator`; it
  does not contain address rules.
- **Never upgrade a name to hide a leak.** Renaming `Notifier` to `MultiChannelNotifier` because it
  now branches on channel is not a solution — the branching is the problem.
- **Generic names are earned, not claimed.** A class deserves one only when a second implementation
  could be dropped in without touching callers.
- **The vocabulary test.** From the name alone, predict which domain words may appear in the body.
  Any word outside that prediction is a leak: `slack`, `vip`, `postgres` inside `save_entity` or
  `calculate_total`.

  ```python
  # WRONG — VIP rule leaked into a generic calculation
  def calculate_total(order: Order) -> Money:
      subtotal = sum(line.price * line.quantity for line in order.lines)
      if order.customer.tier == "vip":
          subtotal *= Decimal("0.9")
      return subtotal

  # CORRECT — the generic function stays generic; the variation is injected
  class DiscountPolicy(ABC):
      @abstractmethod
      def apply(self, subtotal: Money, order: Order) -> Money: ...

  class VipDiscountPolicy(DiscountPolicy):
      @override
      def apply(self, subtotal: Money, order: Order) -> Money:
          return subtotal * Decimal("0.9")

  def calculate_total(order: Order, discount: DiscountPolicy) -> Money:
      subtotal = sum(line.price * line.quantity for line in order.lines)
      return discount.apply(subtotal, order)
  ```

## Names Are Local

A name states what the thing **is or does**, never where it came from, who calls it, or what
happens to it next. A name costs more to fix than a comment, because it is part of the signature
and every call site spells it out.

**The relocation test, applied to a name.** Move the unit to another package and read its name with
the neighbours hidden. A name that stops making sense — or that names a neighbour — was carrying
context that was never its own.

Four kinds leak, and each becomes a lie on a predictable day:

- **The argument's history** — `merged`, `downloaded`, `validated`, `cleaned`. The work is the same
  whatever happened before the call, and the first caller who passes something else makes the name
  wrong.
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
  # WRONG — two of the three names describe the caller's filesystem, not the work
  def convert(merged: Path, runs: Path, *, quality: str) -> Path: ...

  convert(merged_model, project_runs, quality="high")

  # CORRECT — the signature states what the function needs
  def convert(model: Path, into: Path, *, quality: str) -> Path: ...
  ```

  ```python
  # WRONG — the class is named for whoever answers it, the function for whoever calls it
  class AcmeCrmCustomerResponseSchema(BaseModel): ...
  def parse_for_nightly_job(payload: bytes) -> Customer: ...

  # CORRECT — named for what they describe and what they do
  class CustomerRecord(BaseModel): ...
  def parse_customer(payload: bytes) -> Customer: ...
  ```

**The carve-out, and it is narrow.** An implementation *is* named for what makes it concrete —
`SlackNotifier`, `PostgresUserRepository`, `RedisTokenStore`. The vendor is the whole distinction
between it and its siblings behind the same contract. The test still applies: delete the contract,
and the name must still say which implementation this is.

**Values leak too.** A constant whose value names a neighbour ages the same way: a build artefact
whose filename carries the vendor it was derived from outlives that vendor, and every consumer
that mounts the file by name then repeats a claim that stopped being true.

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
