---
paths:
  - "**/*.py"
---

# Naming

Supplement to `core.md`. Governs everything that gets a name.

Case conventions, builtin shadowing, ambiguous single letters and name length are checked by the
project's linters. Nothing below repeats them — this file is about the meaning a name carries, which
no tool can judge.

Examples are taken from `pydantic` and `sqlalchemy`. Both are large, long-lived, and named by
people who then had to live with the choice; where this document and one of them disagree, they
are the stronger evidence.

## General Rules

- **Reveal intent.** A name answers three questions without a comment: what is it, why does it
  exist, how is it used. If a comment is needed to explain the name, the name is wrong.
- **NEVER** use abbreviations, acronyms, or jargon unless universally known (`url`, `id`, `http`,
  `json`, `sql`). Spell it out: `configuration`, not `cfg`; `response`, not `resp`.
- **NEVER** use a vague filler word as the whole name: `data`, `info`, `item`, `object`, `thing`,
  `value`, `result`, `manager`, `helper`, `util`, `misc`, `tmp`, `foo`. A qualified compound is a
  different matter — `pydantic` ships `FieldInfo` and `ComputedFieldInfo`, where `Info` names the
  *description of* a field as opposed to the field itself. `info` alone would name nothing.
- **Length matches scope.** A name living three lines inside a comprehension may be short; a
  module-level name or a public function must be fully explicit.
- **One concept — one word, everywhere.** Pick a single term and never mix synonyms: `fetch` *or*
  `retrieve`, `remove` *or* `delete`, `customer` *or* `client` — never both.
- **Use domain vocabulary**, not generic programmer words (`record`, `entry`, `node`) unless the
  domain itself is generic.
- **Pronounceable and searchable.** Sayable aloud in review, and unique enough to grep for.
- **No cleverness.** No jokes, puns, metaphors, or internal slang.

### Look at the Family Before You Name

Two existing names of the same shape for the same kind of job make that shape a rule: the third
must match it, and any outlier gets renamed. This is checkable mechanically — group by signature
and return kind, then look at whether the names share a shape.

`pydantic` is built this way, and the families are worth copying wholesale:

| Family | Members | What the shape encodes |
|---|---|---|
| namespace prefix | `model_validate`, `model_dump`, `model_dump_json`, `model_copy`, `model_construct`, `model_json_schema`, `model_rebuild` | every method of `BaseModel` is prefixed so a user's own field named `dump` can never collide |
| scope pair | `field_validator` / `model_validator`, `field_serializer` / `model_serializer` | same job, two scopes, one suffix apart |
| input kind | `validate_python`, `validate_json`, `validate_strings` | one verb, the suffix names what is accepted |
| position | `BeforeValidator`, `AfterValidator`, `WrapValidator` | adjective + role, the adjective is the only variable |
| conversions | `to_pascal`, `to_camel`, `to_snake` | `to_` + the target form |

`sqlalchemy` does the same on the query builder:

| Family | Members | What the shape encodes |
|---|---|---|
| derive-a-copy | `with_only_columns`, `with_hint`, `with_statement_hint`, `with_for_update` | `with_` returns a new object that also carries X |
| negated variant | `correlate` / `correlate_except` | `_except` names the complement, so both read the same way |
| symmetric pair | `get_label_style` / `set_label_style` | reader and writer differ by verb only |
| plurality | `scalar` / `scalars` | singular returns one, plural returns many |

A codebase with twelve `salary_in(text)`-shaped names and three `find_salary`-shaped ones has one
concept and two vocabularies. Rename the three.

### Opposites Are Symmetrical

`open`/`close`, `add`/`remove`, `start`/`stop`, `enable`/`disable`, `serialize`/`deserialize`,
`encode`/`decode`. `sqlalchemy` keeps `commit`/`rollback`, `begin`/`close` in exactly these pairs.

## Function and Method Naming

- **One name, one action.** If you need "and" to describe it (`validate_and_save_user`), the
  function violates SRP — split it.
- **Commands are verbs; pure queries may be nouns; participles are banned.** Three cases, and only
  the third is a hard error:
  - A function that *does* something starts with a verb: `normalize_profile`, `send_invoice`.
  - A side-effect-free query may be named after **what it returns**: `pydantic`'s `version_short()`
    and `model_json_schema()`, `sqlalchemy`'s `selected_columns` and `exported_columns`. A noun
    promises purity as reliably as a verb promises action.
  - **NEVER a past participle**: `matched(posting)`, `collapsed(text)`, `grouped(rows)`. The reader
    cannot tell a predicate from a builder — is `matched(posting)` asking or doing? Write the one
    you mean: `is_matched` (question) or `match_posting` (action). Neither library has a name of
    this shape anywhere.
- **The verb names the outcome, not the machinery.** `find_shortest_route`, not `run_dijkstra`;
  `deduplicate_emails`, not `use_set_on_emails`. Implementation changes, intent does not.
- **A generic verb is a design signal, not a naming problem.** `process`, `handle`, `manage`, `do`
  say nothing because the unit does not know what it is for. Neither `pydantic` nor `sqlalchemy`
  has a public `process_*`, `handle_*` or `manage_*`. When the only honest verb is generic, fix the
  responsibility and the name follows.
- **Shortest name that stays unambiguous in context.** Drop what the module, class or parameters
  already convey: `Order.total`, not `Order.order_total`. `sqlalchemy` writes `Session.commit()`,
  not `Session.commit_session()`.
- **The signature completes the sentence.** `find_user(email)`, not `find_user_by_email_string`.
  Use `by_` / `from_` / `to_` only to disambiguate siblings.
- **Predicates read as yes/no questions**: `is_`, `has_`, `can_`, `should_`, `in_`. `sqlalchemy`
  fills this shape densely — `is_active`, `is_derived_from`, `has_identity`, `has_key`,
  `in_transaction`, `in_nested_transaction`. Never negate in the name: `is_valid`, not
  `is_invalid` — callers write `not is_invalid` and readers stumble.
- **Distinguish query from command.** `get_`/`find_`/`compute_`/`is_` are side-effect free;
  `save_`, `update_`, `delete_`, `send_`, `publish_` announce a side effect. Never hide a write
  behind a `get_`.
- **Encode cost and failure mode.** `fetch_`/`load_` imply I/O; `get_` implies a cheap local
  lookup; `compute_` implies CPU work. `find_x` (returns `None` when missing) versus `get_x`
  (raises when missing) must be used consistently across the whole codebase.
- **Conversions read as `to_` / `from_` / `as_`**; classmethod constructors use `from_…`.
- **Async functions are not renamed** — `async def` is visible and the checker enforces `await`.
  Suffix the async one only when both variants live in the same module.
- **Private helpers are still full names.** `_normalize_header`, not `_helper` / `_impl`.
- **Callers must read as prose.** At the call site, without opening the definition, a reader can
  say what happens.

  ```python
  # WRONG — generic verb, hidden side effect, negated predicate, machinery in the name, participle
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

## Variable Naming

- **Nouns for values, plural for collections.** `user`, `users`. Never `user_list`, `users_arr` —
  the annotation already carries the container.
- **Collections name their elements, not their container.** `pending_orders`, not `order_queue`;
  `price_by_sku` for a dict keyed by SKU — the `x_by_y` shape makes the key explicit.
- **Booleans read as predicates**, positive: `is_active`, `has_permission`, `should_refresh`.
  Never `flag`, `status`, `ok`.
- **Quantities carry their unit**: `timeout_seconds`, `file_size_bytes`, `distance_km`,
  `price_usd`. Never a bare `timeout` or `size` when the unit is ambiguous.
- **Loop variables are singular of the collection**: `for order in orders`.
- **Intermediate results are named after what they are, not their stage**: `discounted_price`, not
  `result2` or `price_after_step_3`.
- **Optional values say so in the type, not the name**: `user: User | None`, not `maybe_user`.
- **Constants describe the meaning, not the number**: `MAX_LOGIN_ATTEMPTS = 5`, not `FIVE = 5`.

## Parameter Naming

- Parameters are part of the public API — callers pass them by keyword, so they must be readable
  in isolation.
- **Name the role, not the type**: `recipient: str`, not `string`; `predicate: Callable[…]`, not
  `func`; `on_complete` for a callback.
- **Do not repeat the function name**: `resize(image, width, height)`.
- **Reserved-word clashes take a trailing underscore**, never a misspelling. `sqlalchemy` ships
  exactly this: `is_`, `in_` — not `iz` or `within`.
- **`*args` / `**kwargs` are renamed when they carry meaning**: `*paths: Path`, `**headers: str`.

## Class Naming

- **A noun or noun phrase for the concept**, singular.
- **Name the responsibility.** A suffix earns its place when it names a real role — `pydantic` has
  `AliasGenerator`, `EncoderProtocol`, `GenerateJsonSchema`; `sqlalchemy` has `Session`,
  `Connection`, `MetaData`. A suffix that names nothing does not help: `UserManager` says less than
  `UserRegistration`, `UserDirectory` or `SessionStore`.
- **A family shares the noun and varies the qualifier.** `pydantic`'s URL types are the model:
  `AnyUrl`, `HttpUrl`, `FileUrl`, `FtpUrl`, `AnyWebsocketUrl` — one noun, one axis of variation.
  Same for `AliasPath` / `AliasChoices` / `AliasGenerator`.
- **Describe what it is, not how it is built.** `TaskQueue`, not `RedisTaskQueue` — unless a second
  implementation exists and the distinction is the point.
- **Interfaces start with `Base`.** Every `Protocol` and every ABC whose purpose is to define a
  contract is named `Base` + noun: `BaseNotifier`, `BaseRepository`. The prefix is **mandatory** —
  a contract without `Base`, and a fully implemented class carrying `Base`, are both violations.
- **The concrete class is named by what makes it concrete**: `BaseNotifier` → `EmailNotifier`,
  `SlackNotifier`. A default implementation drops the `Base` and nothing more, when a contract
  exists and exactly one real implementation sits behind it. Where there is no contract at all and
  never will be, name the single class concretely (see Name Matches Abstraction Level).
- **Subclasses extend the parent's name with the distinguishing feature**, reading as "adjective +
  parent": `Cache` → `LruCache`; `ValueError` → `InvalidCurrencyError`.
- **Dataclasses / models are named after the thing they describe**, not the fact that they hold
  data: `Address`, `Coordinates`, `SearchFilters`. Where a project distinguishes several families
  of record by suffix — `OrderModel` for a table, `OrderSchema` for a boundary shape, `OrderDto`
  for transfer between layers — it keeps one such scheme and applies it everywhere, never two.
- **Exceptions name the failure, not the location.** `sqlalchemy`'s hierarchy is the reference:
  `NoSuchColumnError`, `NoSuchModuleError`, `NoReferencedTableError`, `AmbiguousColumnError`,
  `DuplicateColumnError`, `CircularDependencyError` — each says what went wrong precisely enough to
  act on. Never `CustomException`, `MyError`, `Failure`.
- **A package prefix on exceptions is for libraries only.** `PydanticUserError`,
  `PydanticImportError`, `PydanticSchemaGenerationError` earn it: they surface in someone else's
  traceback next to `ValueError`, and the prefix says whose they are. Inside an application, where
  every exception in the traceback is yours, the prefix is noise on every line.
- **Enums are singular nouns; members are states or kinds.** Never plural.
- **Methods drop the class name**: `Order.total()`, not `Order.order_total()`.
- **Properties are nouns, methods are verbs.** A property that does I/O or heavy computation is a
  bug — make it a `fetch_…` / `compute_…` method.

  ```python
  # WRONG — a suffix that names nothing, Base misplaced, plural enum, exception naming no failure
  class DataManager(Protocol): ...     # a contract without Base, and "Manager" says nothing
  class BaseLdapUserDirectory: ...     # Base on a concrete class
  class RequestHandlerBase: ...        # Base is a prefix, and only on a contract
  class OrderStatuses(Enum): ...
  class MyException(Exception): ...

  # CORRECT
  class BaseUserDirectory(Protocol): ...
  class LdapUserDirectory: ...
  class InMemoryUserDirectory: ...
  class RequestHandler: ...            # the suffix names the role
  class UserNotFoundError(LookupError): ...
  ```

## Type, Protocol, and Alias Naming

- **Protocols and contract-ABCs are `Base` + capability name**, usually an agent noun or an
  "-able" adjective: `BaseNotifier`, `BaseSerializer`, `BaseComparable`. Stdlib ABCs (`Iterable`,
  `Mapping`, `Sized`) keep their stdlib names — never wrap one just to add `Base`.
- **Type aliases name the domain meaning**: `type Headers = dict[str, str]`.
- **A kind suffix carries the distinction between related aliases.** `pydantic` names three
  related things three ways: `Color` is the class, `ColorTuple` is the shape,
  `ColorType = ColorTuple | str` is the set of inputs accepted where a colour is expected. The
  suffix is what tells them apart. `…Type` does not mean `type[X]`: a `type[X]` worth naming is
  named for its role (`HandlerByStatus`) or left unaliased at the point of use.
- **Prefer `NewType` over a bare alias** when two values share a runtime type but must not be
  confused: `UserId`, `OrderId` — both `int`, never interchangeable.
- **Type parameters are single capital letters** — `T` by default, `K`/`V` for key/value, `P`/`R`
  for `ParamSpec`/return in decorators. The bound carries the meaning (`[T: BaseModel]`); the
  letter does not need to. Descriptive names are for the rare generic with three or more
  parameters whose roles would otherwise be confused.
- **`TypedDict` follows class rules.**
- **Literal unions get a named alias** when reused.
- **Callback types name the event**: `type OnProgress = Callable[[int, int], None]`.

## Name Matches Abstraction Level — No Logic Leakage

A name fixes the abstraction level of a function or class; the body **MUST** stay at that level.
Logic "leaks" when a generically named thing starts knowing about specific cases, or when a
specifically named thing takes over a sibling's responsibility. Both make the name lie, and a lying
name is worse than no name. This is the naming-side view of SRP and OCP.

- **Generic name → only generic logic.** `BaseNotifier`, `save_entity`, `TaskQueue` must contain
  **no** branching on concrete types, channels, providers, tenants or environments.
- **Concrete logic lives in a concretely named unit, and in exactly one.** Anything Slack-only goes
  in `SlackNotifier`; anything VIP-only goes in `VipDiscountPolicy`.
- **A "special case" branch in a generic body is a design signal, not a fix.** When a generic unit
  needs "but for X do it differently", do one of these — never add the branch:
  1. extract `XSomething` — a separate implementation of the same contract;
  2. move the variation into an injected strategy, policy or callable;
  3. if the variation is data, pass it as data (`discount_rate`), not as a type check.
- **Never re-implement a sibling's responsibility.** `OrderValidator` calls `AddressValidator`; it
  does not contain address rules. If two units hold the same rule, one of them has leaked.
- **Never upgrade a name to hide a leak.** Renaming `Notifier` to `MultiChannelNotifier` because it
  now branches on channel is not a solution — the branching is the problem.
- **Generic names are earned, not claimed.** A class deserves a generic name only when a second
  implementation could be dropped in without touching callers. If there is, and only ever will be,
  one implementation, name it concretely.
- **The vocabulary test.** From the name alone, predict which domain words may appear in the body.
  Any word outside that prediction is a leak: `slack`, `vip`, `postgres` inside `save_entity` or
  `calculate_total` are all violations.

  ```python
  # WRONG — generic name, concrete knowledge inside; every new channel edits this class
  class Notifier:
      def send(self, recipient: Recipient, message: str) -> None:
          if recipient.channel == "slack":
              slack_client.post(recipient.webhook, message)
          elif recipient.channel == "email":
              smtp.send(recipient.address, subject="Notification", body=message)

  # CORRECT — the contract holds only the contract; concrete names hold concrete logic
  class BaseNotifier(Protocol):
      def send(self, recipient: Recipient, message: str) -> None: ...

  class SlackNotifier:
      def send(self, recipient: Recipient, message: str) -> None:
          slack_client.post(recipient.webhook, message)

  class EmailNotifier:
      def send(self, recipient: Recipient, message: str) -> None:
          smtp.send(recipient.address, subject="Notification", body=message)
  ```

  ```python
  # WRONG — VIP rule leaked into a generic calculation
  def calculate_total(order: Order) -> Money:
      subtotal = sum(line.price * line.quantity for line in order.lines)
      if order.customer.tier == "vip":
          subtotal *= Decimal("0.9")
      return subtotal

  # CORRECT — the generic function stays generic; the variation is injected
  class BaseDiscountPolicy(Protocol):
      def apply(self, subtotal: Money, order: Order) -> Money: ...

  class VipDiscountPolicy:
      def apply(self, subtotal: Money, order: Order) -> Money:
          return subtotal * Decimal("0.9")

  def calculate_total(order: Order, discount: BaseDiscountPolicy) -> Money:
      subtotal = sum(line.price * line.quantity for line in order.lines)
      return discount.apply(subtotal, order)
  ```

## Naming Self-Check

Before finishing any piece of code, verify every new identifier against this list:

- [ ] Could a new teammate say what it is without opening its definition?
- [ ] Is it a bare filler word, or a catch-all verb (`process`, `handle`, `do`)?
- [ ] Does it contain an abbreviation that is not universally known?
- [ ] For functions: a precise verb, exactly one action, honest about side effects and cost?
- [ ] For predicates: positive, and phrased as a question?
- [ ] For quantities: is the unit in the name?
- [ ] For collections: plural, and named after its elements?
- [ ] For classes and types: a noun, and does any suffix it carries name a real role? Does every
      `Protocol` / contract-ABC start with `Base`, and no concrete class?
- [ ] Does it match the shape of its family, or is it the outlier that should be renamed?
- [ ] Is the same concept called by the same word everywhere else?
- [ ] Does the body stay at the abstraction level the name promises?
- [ ] Does every concrete rule live in exactly one concretely named unit?
