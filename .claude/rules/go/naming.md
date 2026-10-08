---
paths:
  - "**/*.go"
---

# Naming

No tool judges what a name means. `MixedCaps`, receiver names, `Err`/`Error` affixes, stutter and
printf `f` suffixes are the linters' job: `revive`, `errname`, `goprintffuncname`.

## General

- **Length follows distance.** A name is as long as the gap between its declaration and its last
  use requires: a single letter in a scope of a few lines; a field or an exported function spelled
  out. Beyond a few lines the short names are a closed set — `ctx`, `err`, `ok`, `buf`, `req`,
  `resp`, `cmd`, `tt`, `mu`, `wg`, `tx`, `db`, `w`/`r` in a handler, `t`/`b`/`f` in tests.
  Anything else is spelled out: `settings`, not `cfg`; `response` or `resp`, never `rsp`.
- **Initialisms keep one case**: `userID`, `HTTPClient`, `ServeHTTP`, `parseURL` — never `UserId`.
  An unexported name starting with one lowers all of it: `urlPattern`.
- **The filler words are the same idea one level up**: `util`, `helper`, `common`, `misc`,
  `manager`, `data`, `info` alone. A qualified compound is a real name — `os.FileInfo` names the
  *description of* a file, as opposed to the file.
- **One concept — one word, everywhere.** `Fetch` *or* `Load`, `Remove` *or* `Delete`, `Customer`
  *or* `Client` — never both. **Domain vocabulary**, not `record`, `entry`, `item`.

### Look at the Family Before You Name

Two existing names of the same shape for the same kind of job make that shape a rule: the third
must match it, and any outlier gets renamed. The standard library's shapes are the ones to copy:

- **Variant suffix** — `IndexFunc`, `SortFunc` take a predicate; `QueryContext`, `InfoContext` a
  `ctx`; `strings.SplitSeq` beside `Split` is the lazy form.
- **Append form** — `strconv.AppendInt` beside `FormatInt`: writes into the caller's buffer.
- **Must form** — `regexp.MustCompile`, `uuid.MustParse`: panics instead of returning an error.
- **Derive a copy** — `context.WithTimeout`, `Logger.With`: a new value that also carries X.
- **Iterator methods** — `All`, `Keys`, `Values`, `Backward`, each returning an `iter.Seq`.
- **Parse and format** — `ParseInt`/`FormatInt`, `time.Parse`/`Time.Format`: text in is `Parse`,
  text out is `Format`, `String` or `Append`. **From form** — `netip.AddrFrom4`, `time.UnixMilli`.
- **Opposites are symmetrical** — `Lock`/`Unlock`, `Open`/`Close`, `Marshal`/`Unmarshal`,
  `Encode`/`Decode`, `Commit`/`Rollback`.

A codebase with twelve `ParseDuration`-shaped names and three `DurationFromString`-shaped ones has
one concept and two vocabularies. Rename the three.

## Packages

- **Short, lower-case, one word**, named for what the package *provides*: `orders`, `payroll`,
  `httpauth`. The name is part of every call site — `orders.Find(ctx, id)` — so members do not
  repeat it.
- **Never named for a kind of declaration**: `util`, `common`, `helpers`, `models`, `types`,
  `interfaces`, `base`. Each collects by what things *are*, so everything ends up there and
  nothing can be found. Split it by what the contents are *for*.
- **A package does not take the name its callers need for a variable**: a package `user` steals
  `user` from every function that imports it — `users` or `accounts` does not.

## Functions and Methods

- **One name, one action.** Needing "and" to describe it (`ValidateAndSave`) means it does two.
- **Commands are verbs; a query may be named for what it returns.** `SendInvoice`,
  `NormalizeProfile` do something. A side-effect-free query may be a noun — `time.Since`,
  `Order.Total` — or name the derived result — `slices.Sorted`, `filepath.Clean`. A noun promises
  purity as reliably as a verb promises action.
- **Getters have no `Get`.** The accessor for `owner` is `Owner()`, the setter `SetOwner()`.
- **The verb names the outcome, not the machinery.** `ShortestRoute`, not `RunDijkstra`.
- **A generic verb is a design signal, not a naming problem.** `Process`, `Handle`, `Manage`, `Do`
  say nothing because the unit does not know what it is for. The carve-out is a name the
  framework fixes — `ServeHTTP`, `Mux.Handle`, `Client.Do`.
- **The package and the receiver complete the sentence.** `orders.Find(ctx, id)`, not
  `orders.FindOrderByID`; `Order.Total()`, not `Order.OrderTotal()`. A constructor is `New` when
  the package has one main type (`list.New`), `NewX` otherwise (`http.NewRequest`).
- **Predicates read as yes/no questions** — `IsActive`, `HasPermission`, `CanRetry` — and are
  never negated: `IsValid`, not `IsInvalid`, or callers write `!IsInvalid` and stumble.
- **Absence has one shape per meaning.** `Lookup` returns `(value, ok bool)` when absence is normal
  — `os.LookupEnv`; a name that promises a value returns an error wrapping `ErrNotFound`.
- **Encode cost.** `Fetch`/`Load` imply I/O and take a `ctx`; an accessor is a cheap read;
  `Compute` is CPU work. Never hide a write behind a query-shaped name.

```go
// WRONG — generic verb, Get prefix, negated predicate, machinery, the package repeated
func (s *Service) ProcessProfile(p Profile) Profile
func (o *Order) GetCustomer() Customer
func (j *Job) IsNotReady() bool
func RunLevenshtein(left, right string) int
func FindOrderByID(ctx context.Context, id OrderID) (Order, error) // in package orders

// CORRECT
func (s *Service) NormalizeProfile(p Profile) Profile
func (o *Order) Customer() Customer
func (j *Job) IsReady() bool
func EditDistance(left, right string) int // pure query: named for what it returns
func Find(ctx context.Context, id OrderID) (Order, error) // called as orders.Find
```

## Variables, Parameters and Constants

- **Plural for collections, named for their elements**: `users`, `pendingOrders` — never
  `userList` or `orderQueue`. `priceBySKU` for a map keyed by SKU: `xByY` makes the key explicit.
- **Booleans read as predicates**, positive: `isActive`, `shouldRetry` — never `flag`, `status`.
- **A quantity carries its unit — in the type when Go has one, in the name when it does not.**
  `timeout time.Duration` needs no suffix, because the type is the unit; `timeoutSeconds int` in a
  wire struct, `sizeBytes int64`, `priceCents int64` must say it. A bare `timeout int` is the one
  mistake that produces a plausible result.
- **Intermediate results are named after what they are**: `discounted`, not `result2`.
  **Constants describe the meaning**, in `MixedCaps`: `maxLoginAttempts = 5`, never
  `MAX_LOGIN_ATTEMPTS`.
- **Parameters are named for their role, not their type**: `recipient string`, not `s`;
  `less func(a, b T) bool`, not `fn`. Do not repeat the function name: `Resize(img, width, height)`.

## Types and Interfaces

- **A noun for the concept**, singular — enums too: `OrderStatus`, never `OrderStatuses`. Its
  constants carry the type's name when the package holds several families: `slog.LevelInfo`,
  `http.MethodGet`, `OrderStatusPaid`.
- **Name the responsibility.** A suffix earns its place when it names a real role — `Reader`,
  `Encoder`, `Client`, `Pool`. `UserManager` says less than `Registration` or `Directory`. A family
  shares the noun: `bufio.Reader`, `strings.Reader`, `gzip.Reader`.
- **An interface is named for the capability**, with no `I` prefix and no `Interface` suffix: one
  method is the method plus `-er` — `Reader`, `Notifier`; a larger one is a noun —
  `UserRepository`. The implementations carry the qualifier: `SMTPNotifier`.
- **Never `Base`, `Default` or `Impl`.** Go has no inheritance for `Base` to describe; where an
  interface and its only implementation would collide, the implementation names what makes it
  concrete — its driver, its transport, its storage. If nothing does, the interface was not needed.
- **Errors name the failure, not the location**: `ErrNotFound`, `ErrInsufficientFunds`,
  `*PathError`. The package qualifies them at the call site — `orders.ErrNotFound`.
- **Type parameters are single capitals** — `T`, `K`/`V`, `E` for an element, `S ~[]E` for a slice
  type, as `slices` and `maps` write them. The constraint carries the meaning.

```go
// WRONG — mechanism in the name, a prefix, Base on an interface, a suffix that names nothing
type UserDirectoryInterface interface{ Find(ctx context.Context, email string) (User, error) }
type IUserDirectory interface{ Find(ctx context.Context, email string) (User, error) }
type BaseUserDirectory interface{ Find(ctx context.Context, email string) (User, error) }
type DataManager struct{}

// CORRECT — the interface names the capability, the implementations what makes them concrete
type UserDirectory interface {
	Find(ctx context.Context, email string) (User, error)
}

type LDAPUserDirectory struct{}
type InMemoryUserDirectory struct{}
```

## The Name Fixes the Abstraction Level

A generically named unit — `Notifier`, `SaveEntity`, `CalculateTotal` — holds only generic logic:
no branching on concrete types, channels, providers, tenants or environments. **The vocabulary
test**: from the name alone, predict which domain words may appear in the body; `slack`, `vip` or
`postgres` inside `SaveEntity` is a leak, and a lying name is worse than no name. A special-case
branch is a design signal: make the variation data, an injected func or interface, or a separate
implementation, and keep the concrete rule in exactly one concretely named place. Never
re-implement a sibling's responsibility, and never upgrade a name to hide a leak — a
`MultiChannelNotifier` that switches on the channel still switches.

```go
// WRONG — a VIP rule leaked into a generic calculation
func CalculateTotal(order Order) Cents {
	subtotal := order.Subtotal()
	if order.Customer().Tier == TierVIP {
		return subtotal.Less(10)
	}
	return subtotal
}

// CORRECT — the variation is data; one concretely named place knows about tiers
func CalculateTotal(order Order, discount Percent) Cents {
	return order.Subtotal().Less(discount)
}

func VIPDiscount(customer Customer) Percent
```

## Names Are Local

A name states what the thing **is or does**, never where it came from, who calls it, or what
happens to it next. **The relocation test**: move the unit to another package and read its name
with the neighbours hidden. A name that stops making sense — or that names a neighbour — was
carrying context that was never its own. Four kinds leak, each a lie on a predictable day:

- **The argument's history** — `merged`, `downloaded`, `validated`: the first caller who passes
  something else makes the name wrong.
- **A place in this project** — `runsDir`, `dataDir`, `tmp`. The role is `source`, `into`, `where`.
- **The caller or its intent** — `SaveForUpload`, `ParseForNightlyJob`: a second caller with
  another purpose breaks it.
- **A neighbour's identity** — the vendor, library or sibling package on the other side today. A
  wire struct named after the service that first answered it outlives two replacements of it.

```go
// WRONG — one name carries the argument's history, the other a place in this project
func ArchiveLogs(merged, runsDir string) (string, error)

// CORRECT — the signature states the roles
func ArchiveLogs(source, into string) (string, error)

// WRONG — the type is named for whoever answers it, the function for whoever calls it
type AcmeCRMCustomerPayload struct{}
func ParseForNightlyJob(payload []byte) (Customer, error)

// CORRECT — named for what they describe and what they do
type CustomerPayload struct{}
func ParseCustomer(payload []byte) (Customer, error)
```

**The carve-out, and it is narrow.** An implementation *is* named for what makes it concrete —
`SlackNotifier`, `PostgresUserRepository`. The vendor is the whole distinction between it and its
siblings behind the same interface; delete the interface, and the name must still say which one.

## Naming Self-Check

Before finishing any piece of code, verify every new identifier:

- [ ] Could a new teammate say what it is without opening its definition?
- [ ] Is its length right for the distance to its last use, and is it no filler or catch-all verb?
- [ ] For functions: a verb, or a noun for a pure query; one action; no `Get`; honest about cost —
      and does the package name complete it without repeating it?
- [ ] For predicates: positive, a question? For quantities: the unit in the type or the name?
- [ ] For types: a noun, a suffix with a real role, an interface named for its capability, no
      `Base`, `Default` or `Impl`?
- [ ] Does it match the shape of its family, and the word used for this concept everywhere else?
- [ ] Does the body stay at the abstraction level the name promises?
- [ ] Does it survive the relocation test — no history, place, caller or neighbour in it?
