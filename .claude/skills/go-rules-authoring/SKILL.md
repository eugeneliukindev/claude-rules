---
name: go-rules-authoring
description: >-
  Conventions for writing and auditing the Go coding rules in .claude/rules/go/*.md and the go-*
  skills: which conventions are shared with the Python rules and where they live, what loads when
  for Go files, the line budget, examples that compile and pass vet and the linters at the
  declared Go version, verifying API claims with go doc instead of memory, and porting a rule from
  another language only when Go's own idiom agrees. Use when editing, adding to, splitting,
  auditing or evaluating the Go rule files or go-* skills.
---

# Writing the Go Rules

## What Is Shared, and Where It Lives

The method is the same for every language, and it is written once, in `python-rules-authoring`:
**How a Rule Is Written** (widest category, carve-out beside the prohibition, the failure mode,
invented and real examples, the pair differing in one dimension, no project names), **What Holds
These Rules Up**, **One Rule, One Home**, **A Skill's Description Is Its Trigger**, and
**Evaluation Before and After**. Read those sections before changing a Go rule; this file holds
only what is different for Go.

## What Loads When

| file | loads |
|---|---|
| `rules/go/core.md`, `naming.md`, `functions.md`, `control-flow.md`, `types.md`, `methods.md`, `interfaces.md`, `packages.md`, `errors.md`, `logging.md`, `comments.md` | together, on the first read of any `**/*.go` |
| `rules/go/testing.md` | on a read of `**/*_test.go`, `**/testdata/**` or `**/*test/*.go` |
| `rules/go/new-files.md` | every session — six lines, for the module written into an empty directory |
| `skills/go-*/SKILL.md` | when the description matches the work, or by `/name` |

The budget, counted without front matter:

| file | ceiling |
|---|---|
| `naming.md` | 300 |
| any other rule file | 120 |
| **everything loaded on every `.go`** | **800** |
| any one `SKILL.md` | 500 |

The numbers are the Python set's, for the Python set's reasons; the Go set reached 880 lines on its
first draft and was cut to 800 by tightening prose, not by dropping rules. **An addition displaces
something**, and what cannot displace anything becomes a skill with a row in `core.md`'s map.

## Every Go Example Compiles

**A `CORRECT` is real Go**: it compiles at the `go` version the rules assume, `go vet` is clean,
and the linters the rules name — `errcheck`, `errorlint`, `revive`, `gocritic`, `nilnil`, `gosec`,
`modernize` — have nothing to say about it beyond what a fragment cannot satisfy: a package
comment, doc comments on declarations the example is not about, a name nothing in the fragment
uses, and `errcheck` on a deferred reader `Close` (`packages.md`). The first full run found
`http.NoBody` missing where a request had no body. Fragments are checked the way a reader would
use them:

- **A fragment of statements** is pasted into a function body with the variables it names declared
  above it.
- **A bare signature** — `func Find(ctx context.Context, id OrderID) (Order, error)` with no body —
  stands for a declaration whose body is not the point, and is checked with `{ panic("") }`
  appended.
- **The types an example names but does not declare** — `Order`, `Cents`, `Notifier` — get the
  smallest declaration that makes it compile, in a scratch file beside it.
- **The toolchain is the one the rules target, not the one installed**: in a scratch module with
  `go 1.27` in its `go.mod`, `GOTOOLCHAIN=go1.27.1 go vet ./...` downloads and uses it. A local
  `GOROOT` from a version manager overrides that and must be unset first.

A `WRONG` compiles too, unless the mistake it shows is a compile error. A wrong example that does
not compile teaches nothing about the bug it was meant to show — the compiler would have caught it.

## API Claims Come from `go doc`, Not Memory

Every function, option, tag and version number in these files is checked with `go doc` at the
target version before it is written. Four claims in the first draft of this set were written from
memory and wrong: the standard `uuid` package has no `NewString`; `testing/synctest` fails a test
whose bubble deadlocks rather than reporting leftover goroutines; `type OrderID uuid.UUID` drops
every method of `UUID`; and `url.URL.JoinPath` does not escape its segments — an example built on
that claim let an ID of `../admin` leave the path, in the skill about HTTP clients. A behaviour claim is checked
by running ten lines, not by reading: that is how `encoding/json/v2` turned out to have no default
representation for `time.Duration` — it fails rather than writing nanoseconds as v1 does.

**Every version-specific statement names its version** — "since Go 1.27", "(Go 1.25)" — so a
reader on an older `go` line knows which advice does not yet apply to them, and an audit after
the next release knows what to re-check.

## Porting a Rule from Another Language

A rule that is right in Python is a hypothesis in Go, and the standard library is the test. Port
it only where Go's own code agrees; where it does not, write the Go rule and say why. The first
port found four that do not survive:

- **"Never a past participle as a function name"** — Python's reference libraries have none; Go's
  standard library has `slices.Sorted` and `slices.SortedFunc` by design. Dropped.
- **"Spell it out"** — Go names are as long as their scope: `r`, `w`, `ctx` and `buf` are the
  idiom. Replaced by length-follows-distance with a closed list of short names.
- **"A contract is an ABC the implementations inherit"** — Go interfaces are satisfied implicitly
  and declared by the consumer. Replaced by consumer-side interfaces and a compile-time assertion
  where a producer must conform.
- **"`kw_only=True` on every dataclass"** — Go has no keyword arguments, but keyed struct literals
  carry the same protection. Ported as "struct literals always name their fields".

The opposite also happens: a rule with no Python counterpart because the risk does not exist
there — `ctx` as the first parameter, an owner for every goroutine, `nil, nil`. Those are written
from Go's own idiom and the Go Code Review Comments, never adapted from elsewhere.
