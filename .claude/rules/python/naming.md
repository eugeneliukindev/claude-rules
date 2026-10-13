---
paths:
  - "**/*.py"
---

# Naming

Every line of code names something, and no tool judges the meaning a name carries. Case, builtin
shadowing, single letters, length and the filler-word blacklist are the linters' job.

## General

### A name is spelled out, in the domain's words

**Why:** `cfg`, `resp` and `tmp` make the reader decode; `manager`, `helper`, `util`, `misc` are the
fillers the linter misses, naming nothing; `record`, `entry`, `node` are programmer words where the
domain has its own.
**Except:** universally known abbreviations — `url`, `id`, `http`, `json`, `sql`; a qualified
compound is a real name — `FieldInfo` names the *description of* a field, where `info` alone would
name nothing.

**Example:**
```python
# WRONG — abbreviations, a filler and a programmer word
@final
class StockMgr:
    def __init__(self, *, cfg: WarehouseSettings) -> None:
        self._cfg = cfg

    def get_rec(self, sku: Sku) -> StockRecord:
        return self._cfg.store.load(sku)


# CORRECT — the domain's words, spelled out
@final
class StockLedger:
    def __init__(self, *, storage: StockStorage) -> None:
        self._storage = storage

    def find_stock_level(self, sku: Sku) -> StockLevel:
        return self._storage.load(sku)
```

### One concept has one word everywhere, and a name matches the shape of its family

**Why:** `fetch` *and* `retrieve`, `patient` *and* `client` in one codebase make the reader wonder
whether they differ. Two names of one shape for one kind of job make the shape a rule — group by
signature and return kind to see it (the shapes worth copying: `python-packaging`); the third
matches, and an outlier is renamed now — a library that waited renamed `isnot` to `is_not` and still
carries every old name as an alias.

**Example:**
```python
# WRONG — two verbs and two nouns for one idea
def fetch_patient(patient_id: PatientId, *, records: PatientRecords) -> Patient:
    return records.patient(patient_id)


def retrieve_client_appointments(client_id: PatientId, *, records: PatientRecords) -> list[Visit]:
    return records.appointments(client_id)


# CORRECT — one verb, one noun, one shape
def fetch_patient(patient_id: PatientId, *, records: PatientRecords) -> Patient:
    return records.patient(patient_id)


def fetch_patient_appointments(patient_id: PatientId, *, records: PatientRecords) -> list[Visit]:
    return records.appointments(patient_id)
```

## Variables and Parameters

### A value is a noun, a collection a plural named for its elements, a boolean a predicate

**Why:** `user_list` repeats the annotation; `invoice_queue` names the container, not what is in
it — `pending_invoices`, and `rate_by_currency` where the `x_by_y` shape says the key. A loop
variable is the singular, a boolean is `is_active`, never `flag` or `ok`; an intermediate result is
named for what it is (`discounted_total`, not `result2`); optional is said by the type, never
`maybe_user`; a constant names its meaning, `MAX_LOGIN_ATTEMPTS`, not the number.

**Example:**
```python
# WRONG — the container, a stage and a flag instead of what the values are
def apply_discounts(invoice_list: list[Invoice], data: dict[str, Decimal]) -> list[Decimal]:
    result: list[Decimal] = []
    for x in invoice_list:
        flag = x.customer_id in data
        result2 = x.total * (1 - data[x.customer_id]) if flag else x.total
        result.append(result2)
    return result


# CORRECT — each name says what the value is
def apply_discounts(
    invoices: Iterable[Invoice], discount_by_customer: Mapping[CustomerId, Decimal]
) -> list[Decimal]:
    discounted_totals: list[Decimal] = []
    for invoice in invoices:
        discount = discount_by_customer.get(invoice.customer_id, Decimal(0))
        discounted_totals.append(invoice.total * (1 - discount))
    return discounted_totals
```

### A quantity carries its unit in the name

**Why:** the reader of a call site has the name and nothing else, and a wrong unit is the one
mistake that produces a plausible result — in every kind of name: `timeout_seconds`,
`MAX_UPLOAD_BYTES`, `price_usd`.
**Except:** a `timedelta` carries its unit in the type; a name that repeats a standard's —
`timeout` in float seconds as the stdlib uses it, a cookie's `max_age` — needs none.

### A parameter names its role, not its type

**Why:** callers pass parameters by keyword, so a parameter must read in isolation — `recipient`,
not `string`; `predicate`, not `func`; `on_complete` for a callback; never the function's name
again. A reserved word takes a trailing underscore, never a misspelling (`sqlalchemy` ships `is_`,
`in_`); `*args` and `**kwargs` are renamed when they carry meaning: `*paths`, `**headers`.


## Functions and Methods

### A command is a verb naming its outcome; a pure query may name what it returns

**Why:** a verb promises an effect and a noun promises none — `send_invoice`, but `math.hypot()`,
`Select.subquery()`, `sorted()`. The verb names the outcome, not the machinery: implementation
changes, intent does not. A generic verb — `process`, `handle`, `manage`, `do` — is a design signal:
the unit does not know what it is for, so fix the responsibility and the name follows. Needing
"and" means two functions.
**Except:** never a participle that reads as a predicate — `matched(payment)`, `validated(invoice)`
leave the reader unable to tell a question from a builder; this is about callables only — a variable
or an alias may be `discounted_price`.

**Example:**
```python
# WRONG — a generic verb, the machinery, and a participle that reads as a question
def process_payment(payment: Payment) -> Payment:
    return replace(payment, amount=payment.amount.quantize(_CENT))


def run_levenshtein(left: str, right: str) -> int:
    return _levenshtein(left, right)


def matched(payment: Payment, *, statement: BankStatement) -> StatementLine | None:
    return statement.line_for(payment.reference)


# CORRECT — the outcome, a noun for a pure query, a verb for the match
def round_payment(payment: Payment) -> Payment:
    return replace(payment, amount=payment.amount.quantize(_CENT))


def edit_distance(left: str, right: str) -> int:
    return _levenshtein(left, right)


def match_payment(payment: Payment, *, statement: BankStatement) -> StatementLine | None:
    return statement.line_for(payment.reference)
```

### A predicate is a positive yes-or-no question

**Why:** `is_`, `has_`, `can_`, `should_`, `in_` read as questions; a negated name makes callers
write `not is_invalid`, and readers stumble.

### The prefix tells the cost and the side effect; the return type tells the failure

**Why:** `get_` is a cheap local lookup, `find_` a search that may find nothing, `fetch_` and
`load_` do I/O, `compute_` is CPU work, and `save_`, `send_`, `publish_` announce a write — never a
write behind a `get_`. Normal absence is `-> User | None`, which the checker makes every caller
handle; absence that is a bug raises behind `-> User`, so no prefix repeats the annotation.
Conversions read `to_`, `from_`, `as_`, and classmethod constructors are `from_…`; an `async def`
is not renamed, since the checker enforces the `await`.
**Except:** a method of a store contract keeps its family's verbs, and the contract says it does
I/O — a repository's `get` raises when the row is missing and its `find` returns `None`; a cache's
`get` returns `None` on a miss, as `dict.get` does.

**Example:**
```python
# WRONG — a getter that does I/O and writes an audit row
def get_report(report_id: ReportId, *, reports: ReportStore, audit: AuditLog) -> Report:
    audit.record_access(report_id)
    return reports.download(report_id)


# CORRECT — the I/O and the write each named for what they do
def fetch_report(report_id: ReportId, *, reports: ReportStore) -> Report:
    return reports.download(report_id)


def record_report_access(report_id: ReportId, *, audit: AuditLog) -> None:
    audit.record_access(report_id)
```

### A hook is named for the event it receives; an override keeps the framework's name

**Why:** a callback the framework calls — `before_request`, `on_startup` — is found by its event;
an override renamed to something "better" is no longer an override.

### The shortest name that stays unambiguous, completed by its signature

**Why:** what the module, the class or the parameters already say is dropped — `Recipe.name`, not
`Recipe.recipe_name`; `find_user(email)`, not `find_user_by_email_string`; `by_`, `from_`, `to_`
only to tell siblings apart. A private helper is still a full name: `_normalize_header`, never
`_helper`.

**Example:**
```python
# WRONG — the class repeated in every name
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Recipe:
    recipe_name: str
    recipe_calories: int
    recipe_servings: int

    def calculate_recipe_calories_per_serving(self) -> float:
        return self.recipe_calories / self.recipe_servings


# CORRECT — the class finishes the sentence
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Recipe:
    name: str
    calories: int
    servings: int

    def calories_per_serving(self) -> float:
        return self.calories / self.servings
```

## Classes and Types

### A class is a singular noun naming its responsibility

**Why:** a suffix earns its place when it names a real role — `Session`, `Connection`,
`AliasGenerator`; `DataManager` says less than `DocumentArchive`. An enum is the singular kind, its
members states or kinds; a dataclass is named for the thing it describes, not for holding data. A
project that tells families apart by suffix — `InvoiceRow` for a table, `InvoiceSchema` for a
boundary shape — keeps one scheme everywhere, never two. Contracts and their implementations are
named as `python-contracts` says.

**Example:**
```python
# WRONG — a suffix that names nothing, a plural enum, a container for a name
@final
class DocumentManager:
    def __init__(self, *, storage: ObjectStorage) -> None:
        self._storage = storage

    def keep(self, document: Document) -> str:
        return self._storage.put(document.document_id, document.content)


class DocumentStatuses(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


# CORRECT — the noun names the responsibility; the enum is the singular kind
@final
class DocumentArchive:
    def __init__(self, *, storage: ObjectStorage) -> None:
        self._storage = storage

    def keep(self, document: Document) -> str:
        return self._storage.put(document.document_id, document.content)


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
```

### A family shares the noun and varies the qualifier; a subclass reads "adjective + parent"

**Why:** the stdlib's `ipaddress` is the model — `IPv4Address`, `IPv6Address`, `IPv4Network`: the
noun names the concept, the qualifier the one axis that varies — and `Cache` → `LruCache`,
`ValueError` → `InvalidCurrencyError` say what the subclass adds.

### An exception names the failure, and only a library prefixes it

**Why:** `sqlalchemy`'s `NoSuchColumnError`, `CircularDependencyError` say what went wrong precisely
enough to act on; `BillingServiceError` says where. `PydanticUserError` earns its prefix in someone
else's traceback; in an application every exception in the traceback is yours, and the prefix is
noise — the package's root exception is the one name that carries it, in both (`errors.md`).

### A method drops the class name; a property is a noun that does no I/O

**Why:** `invoice.total()` already says whose total; a property reads like a field, so I/O or heavy
work behind one surprises every caller — that is a `fetch_…` or `compute_…` method.

**Example:**
```python
# WRONG — the class repeated, and a network call behind attribute syntax
@final
class Customer:
    def __init__(self, *, customer_id: CustomerId, crm: CrmClient) -> None:
        self._customer_id = customer_id
        self._crm = crm

    def customer_name(self) -> str:
        return self._crm.name(self._customer_id)

    @property
    def credit_limit(self) -> Decimal:
        return self._crm.credit_limit(self._customer_id)


# CORRECT — the method named for what it returns, and the I/O announced by its verb
@final
class Customer:
    def __init__(self, *, customer_id: CustomerId, crm: CrmClient) -> None:
        self._customer_id = customer_id
        self._crm = crm

    def name(self) -> str:
        return self._crm.name(self._customer_id)

    def fetch_credit_limit(self) -> Decimal:
        return self._crm.credit_limit(self._customer_id)
```

### A type alias names the domain meaning; a `NewType` keeps apart values of one runtime type

**Why:** `type Headers = dict[str, str]` says what the dict is; two ids that are both `str` are
swapped silently unless each is its own `NewType`. A structural type describing someone else's
shape takes `-Like` (`os.PathLike`); related aliases are told apart by a kind suffix — `ColorTuple`
for the shape, `ColorInput` for the accepted inputs. Type parameters are named in `python-types`.

**Example:**
```python
# WRONG — two str ids that the checker cannot tell apart
def assign_parcel(tracking_number: str, courier_id: str) -> None:
    _assignments[tracking_number] = courier_id


assign_parcel(courier_id, tracking_number)


# CORRECT — each id its own type; the swapped call is an error
TrackingNumber = NewType("TrackingNumber", str)
CourierId = NewType("CourierId", str)


def assign_parcel(tracking_number: TrackingNumber, courier_id: CourierId) -> None:
    _assignments[tracking_number] = courier_id
```

## The Name Fixes the Abstraction Level

### A generically named unit holds only generic logic

**Why:** from the name alone a reader predicts which domain words may appear in the body —
`slack`, `vip` or `postgres` inside `calculate_total` is a leak, and a lying name is worse than
none.
A special-case branch is a design signal: the variation becomes data, an injected strategy or a
separate implementation, and the concrete rule lives in one concretely named place. A sibling's
responsibility is called, never re-implemented; a name is never upgraded to hide a leak — a
`MultiChannelNotifier` that branches on the channel still branches.

**Example:**
```python
# WRONG — a VIP rule leaked into a generic calculation
def calculate_total(invoice: Invoice) -> Decimal:
    subtotal = sum((line.amount for line in invoice.lines), start=Decimal(0))
    if invoice.customer_tier == "vip":
        return subtotal * Decimal("0.9")
    return subtotal


# CORRECT — the variation is data; one concretely named place knows about tiers
def calculate_total(invoice: Invoice, *, discount_rate: Decimal) -> Decimal:
    subtotal = sum((line.amount for line in invoice.lines), start=Decimal(0))
    return subtotal * (1 - discount_rate)


def vip_discount_rate(tier: CustomerTier) -> Decimal:
    return _VIP_DISCOUNT if tier is CustomerTier.VIP else Decimal(0)
```

## Names Are Local

### A name says what the thing is or does — never its history, place, caller or neighbour

**Why:** a name is part of the signature and every call site spells it out, so it costs more to fix
than a comment. Move the unit to another package and read its name with the neighbours hidden: the
argument's history (`merged`, `cleaned`) turns false for the next caller; a place in this project
(`runs`, `data_dir`) names one repository's layout; the caller's intent (`for_nightly_job`) breaks
for a second caller; a neighbour's identity — a schema named after the vendor that first answered
it — outlives two replacements of the vendor.
**Except:** an implementation *is* named for what makes it concrete — `SlackNotifier`,
`PostgresUserRepository`; delete the contract, and the name must still say which one it is.

**Example:**
```python
# WRONG — the argument's history, a place in this project, the caller, the vendor
def archive_statements(merged: Path, runs: Path) -> Path:
    return Path(shutil.make_archive(str(runs / merged.stem), "zip", merged))


def parse_for_nightly_job(payload: bytes) -> Customer:
    return AcmeCrmCustomerSchema.from_json(payload).to_domain()


# CORRECT — the signature states the roles; each name says what it describes or does
def archive_statements(source: Path, *, into: Path) -> Path:
    return Path(shutil.make_archive(str(into / source.stem), "zip", source))


def parse_customer(payload: bytes) -> Customer:
    return CustomerSchema.from_json(payload).to_domain()
```

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
- [ ] Does it survive the relocation test (Names Are Local, above) — no history, place, caller or
      neighbour?
