---
name: python-rules-authoring
description: >-
  Writes and audits these Python rules and skills: the rule format, examples, one home per rule,
  descriptions, what loads when, budgets. ALWAYS invoke this skill when editing, adding, splitting
  or auditing a file under rules/python or a python-* skill. Do not edit these rules directly.
paths:
  - "**/rules/python/**"
  - "**/skills/python-*/**"
---

# Writing These Rules

These files are read while writing code, under time pressure, by someone already holding a
different problem in their head. A rule that is technically correct and easy to misread will be
misread; a rule breaking one of the conventions below is a defect **in this document**, fixed here
rather than worked around in code. The incidents behind the conventions are in
docs/rules-history.md in the repository, evidence for people rather than instructions.

### Every rule is a heading and a `**Why:**`, and an `**Example:**` only where it earns its place

**Why:** a fixed hierarchy lets the reader find the part they need without reading the rest. The
heading is the rule, one sentence, `###` under the topic's `##`; the `**Why:**` is what breaks, and
when, since the model generalises from the motivation; the `**Example:**` is the `# WRONG` and
`# CORRECT` pair, a carve-out one more `# CORRECT` or one `**Except:**` sentence before it. The
prose is at most 700 characters, aim 600, the example not counted: past that it is two rules or a
lecture.

**Example:**
``````markdown
<!-- WRONG - a bold bullet with the reason and the example scattered around it -->
- **Collaborators arrive through the constructor.** This matters for tests, as discussed in the
  testing section; see the example further down.

<!-- CORRECT - the rule, what breaks, and the pair -->
### Collaborators arrive through the constructor

**Why:** one built inside cannot be replaced in a test, and its signature hides what it needs.

**Example:**
```python
# WRONG - the repository is built inside: no test can hand in a fake
@final
class IceCoreArchive:
    def __init__(self, *, engine: AsyncEngine) -> None:
        self._cores = PostgresCoreSampleRepository(engine)

# CORRECT - it arrives from the composition root
@final
class IceCoreArchive:
    def __init__(self, *, cores: CoreSampleRepository) -> None:
        self._cores = cores
```
``````

### An example is written only where the model gets the code wrong without it

**Why:** every example is one more place another rule can contradict, and each is checked against
all of them. One earns its place by a measured fact, a decision the model would not make, or a shape
the heading cannot show - an actor split, a contract suite, guards first; a heading that already
says the code - `Final` on a constant, the unit in a name - has none. Undecided, an always-loaded
rule keeps its example and a skill's rule drops it. A list that *is* the rule - the module order -
stays a list; prose the example already shows, a restatement or history is cut.

### A rule is stated over the widest category it is true for

**Why:** a rule written about a class gets applied to classes and to nothing else - the reader
cannot tell whether the other kinds were excluded deliberately or never considered. The
encapsulation rule said "class" for months, and the cost was twenty-eight public names nobody
imports. Name every kind it covers, and let the examples illustrate, never define.

### Every prohibition carries its carve-out in the same place

**Why:** "never name a vendor" and "implementations are named for what makes them concrete" are both
true, and a reader who meets the first without the second renames `SlackNotifier`. An exception
three sections away, or in another file, does not exist; two skills that state a rule and its
exception apart are two contradictory rules.

### The `**Why:**` says what breaks and when, with a real incident where one exists

**Why:** "names are local" is an opinion; "the model was replaced twice and the name outlived both"
is a cost with a date on it. The failure mode lets a reader settle an edge case alone. An incident
is never invented to fill the slot: an invented one teaches a failure nobody has seen.

### An example is complete code, and the pair differs only in what the rule is about

**Why:** the model copies the example, not the prose. A fragment teaches the shape of a fragment,
so a method appears inside its `class` with the fields and constructor it uses, and a body is the real one wherever the body is the point.
A `WRONG` that also lacks annotations, uses a global and swallows an error leaves eight differences,
and the reader copies all eight. Imports and the declarations of names an example uses are omitted
in every file.

### A `CORRECT` obeys every other rule here, parses, and runs

**Why:** where a rule and an example disagree, the model has two instructions and picks one
arbitrarily - `kw_only`, `@override`, `Final`, the `_` prefix, units in names and injected
dependencies hold in every `CORRECT`, and so does a setting defaulted in the signature of whatever
reads it (`functions.md`). An API claim from memory taught `orjson` serialising `Decimal`, so a
block is run in a scratch file against the library version the skill names before commit.

### Examples vary their domain, and neither half names a project

**Why:** the model copies the surface too: one practitioner traced a pattern from 0.3% of the input
to 36% of the output through a single example line, and an audit found 43% of these files' Python
blocks built on orders. One domain holds within a skill whose examples build on each
other, and no domain more than about a sixth of all blocks. These files are read in every
repository, so no entity, vendor or identifier of the project at hand appears - the shape of the
incident carries the lesson, its names carry none of it.

### An example's names belong to one skill, and none to a rule file

**Why:** a class shown in two skills is one construction taught twice, and the model takes the
repetition for the house pattern: the audit found about 130 shared names - `AppSettings` and
`open_database_pool` in five skills, `DocumentArchive` in a rule file and a skill. Every function,
class and constant an example defines or calls is its skill's alone; names a framework or the
language fixes - `main`, `lifespan`, `Settings` - are allowed everywhere. A clash is renamed in the
skill, and in a rule file only when the skill cannot.

### A rule leads with the positive, states its reason, and saves capitals for nothing

**Why:** naming the thing to avoid makes it more available, not less, so the positive leads and the
`# WRONG` carries the negative; a bare `NEVER` is kept for a rule whose right answer is not obvious
from the positive alone. Capitals make current models over-apply a rule to cases it was never meant
for, and a file where every second line says `MUST` has no emphasis left; the reason does the work.

### A new rule says whether it holds in a one-off script

**Why:** these files are written for code that lives, and the model applies them to a forty-line
one-off as readily as to a service. `python-scripts` lists what relaxes there and what never does; a
new rule that would be ceremony in a script joins the first list in the same change, and one that
protects data, money or a credential joins the second.

### `scripts/check_rules.py` runs before every commit

**Why:** a budget counted by eye was broken by six lines before anyone noticed. The script checks the
budgets - always-loaded, each `SKILL.md`'s 500 lines and 6,000 tokens, each rule's 700 characters
of prose; that blocks parse and named files exist; front matter and descriptions; where skills
name each other; library API and shared names in examples; and the mechanical rules in every
`CORRECT` - `Final`, dataclass flags, aware `now()`, settings defaulted, not passed. A finding is
`path:line: message`, exit 1; that a `CORRECT` runs is checked by hand.

## Where a Rule Lives

Two mechanisms, and which one a file lives in is the decision:

| | rule, `paths:` in front matter | rule, no front matter | skill |
|---|---|---|---|
| lives in | `~/.claude/rules/` | `~/.claude/rules/` | `~/.claude/skills/<name>/SKILL.md` |
| enters context | when a matching file is read | at launch, every session, every language | listed once a file matching its `paths` is read or written; loaded when its `description` matches the work, or by `/name` |
| always costs | nothing | its whole length | its `description`, and only after `paths` match |

The always-loaded set has a hard budget, counted in what costs adherence - instruction-following
falls as the number of instructions grows, and an example is tokens but not an instruction:

| what | ceiling |
|---|---|
| **rules loaded on every `.py`** - `###` headings, or top-level bold bullets in a file not yet in that format | **100** |
| **tokens loaded on every `.py`**, estimated at four characters each | **22,000** |
| rules loaded on a test file - the set above plus `testing.md` | 120 |
| tokens loaded on a test file | 28,000 |
| lines in any one `SKILL.md`, after the front matter | 500 |
| tokens in any one `SKILL.md`, after the front matter | 6,000 |

Anthropic's authoring guidance and the Agent Skills specification ask for under 500 lines and 5,000
tokens, which Claude Code re-attaches after compaction; 6,000 leaves only a short tail to lose, the
price of keeping a skill in one file.

### What applies to every edit is a rule file with `paths: "**/*.py"`, one topic per file

**Why:** a rule with no front matter is the documented instruction to load it into every session in
every language, and it is the easy mistake: sixteen files once sat there at once, and
nothing noticed. The always-loaded files - `core.md`, `naming.md`, `types.md` and the rest - load
together on the first read, `testing.md` on its own test-file globs; splitting them by topic changes
the organisation, not the cost, so one splits only to give a rule its own address.

### `new-files.md` is the one file with no front matter, and the exception is measured

**Why:** a path-scoped rule loads when a matching file is *read*; a task that writes `x.py` into an
empty directory reads nothing, and in measured runs such tasks went without the rules. Its six lines
cost every session in every language; they buy the rules for the one case the glob cannot see.

### Every skill carries `paths`, so a session lists only the skills of its language

**Why:** without it every description sits in every session's listing - the Go skills in a Python
repository - where a better-matching wrong one displaces the right one. Measured on Claude Code 2.1.118: a skill with
`paths: "**/*.py"` is absent from the listing, and `Unknown skill` when called, until a `.py` file
is read *or written*. The default is `**/*.py` and `**/pyproject.toml`; a skill whose work lives in
other files adds them, and `/name` works whatever `paths` says.

**Example:**
```yaml
# WRONG - no paths: listed in every session, in every language
name: python-scripts
description: ...

# CORRECT - listed once Python or a notebook is touched
name: python-scripts
description: ...
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/*.ipynb"
```

### The skills hold design, and no skill is about a library

**Why:** the always-loaded core holds what every edit needs, typing included, and seven skills the
design only some work reaches - contracts, wiring, boundaries, security, scripts, review and
authoring. Fifteen library skills went stale faster than they were checked: an API changes with
every release. A library's traps come from its current documentation, fetched at the time
(context7), and from its tests; a design skill's example is written against its own contracts, so
it holds whatever library serves it.

### The always-loaded set holds what is universal and behaviour-changing, with its examples

**Why:** every edit pays for an always-loaded rule, so it earns that by being universal - every
Python file could break it - and behaviour-changing - without it the obvious default is wrong. A
rule only some paths reach is a skill with a row in the map. But a skill loads only when the work
names its topic: with the examples for functions, classes, errors and comments moved into skills,
the measured layout lost almost every run. What moves is what a concrete signal in the task points
at - an outbound call, an entry point, an untrusted input, a one-off script.

### An addition displaces something, and a ceiling is raised only by an argument on record

**Why:** without a fixed number every addition looks free, and a file once grew to three thousand
lines one paragraph at a time. A new rule cuts what it makes redundant, an example that stopped
earning its tokens, or a section that belongs in a skill; if nothing can be cut, it becomes a
skill. The budget counts the set, not the file. A ceiling is raised once per good argument, written
into docs/rules-history.md with the arithmetic - one adjusted to fit the current size is none.

### A skill is one `SKILL.md`, and what does not fit is cut, not moved

**Why:** in our evals a linked file was read in one or two runs of eight, so a rule moved there is a
rule most runs never see. A second skill for the same trigger is no better: its description
competes in a listing capped at 1% of the context window, least-invoked dropped first. A second
skill is for a second trigger; halves one task needs together stay one skill. A body past 500 lines
or 6,000 tokens loses what the model does unprompted, rules said twice and examples the heading
already shows, until it fits.

**Example:**
````markdown
<!-- WRONG - the rule moved into a file the model opens in a minority of runs -->
## Time

**Before writing code that creates or compares a `datetime`, read time.md.**

<!-- CORRECT - the rule itself, in the body that loads -->
## Time

### A `datetime` is aware and in UTC

**Why:** a naive one is compared with an aware one and raises, or is stored in local time.
````

### A rule no tool checks either becomes a check or is deleted, once it is broken in bulk

**Why:** a rule nothing checks rests on attention, and nothing fails when it is skipped. A rule broken by
the dozen is a wish, not a standard: write the check, or delete the rule. Between the two sits a
procedure - the Definition of Done in `core.md`, which `python-review` walks over a diff - and a
rule that belongs on that list is added to both.

## One Rule, One Home

### A rule is written in exactly one file, and a skill never restates a rule file

**Why:** three copies of the retry policy drift into three policies; two files that disagree about
where a test fake lives get one of them followed at random. The rule files load on every `.py`, so
a skill cites one in a clause - "(`errors.md`)" - and repeats none of it; where they contradict,
the rule wins and the skill is fixed.
Between two skills a rule has one owner; the other drops it, and a case where it differs is an
`**Except:**` of its own rule.

### A skill names a neighbour only in its introduction, once, as a route

**Why:** naming a skill does not load it - Anthropic's guidance says skills cannot reference each
other - so a "see python-x" inside a rule points the reader at text they do not have, and the
rule reads as incomplete. The introduction, between the title and the first heading below it,
routes work that started in the wrong skill; a carve-out is an `**Except:**` sentence in the rule it
qualifies. `scripts/check_rules.py` reports a skill named anywhere else.

### A library's lifetime is the library's own context manager

**Why:** `python-wiring` once named a lifetime `managed_pool`, the other skills repeated it -
`managed_redis`, `managed_grpc_server` - and the model learned the prefix and wrapped libraries that
already had one. The
root enters what the library ships - `async with asyncpg.create_pool(...)`, `async with broker:`. A
hand-written `@contextmanager` or `@asynccontextmanager` is for a library that has none, and is
named for what it yields, never with a fixed prefix.

**Example:**
```python
# WRONG - a wrapper around a context manager the library already has, under a house prefix
@asynccontextmanager
async def managed_survey_pool(*, dsn: str) -> AsyncIterator[asyncpg.Pool]:
    pool = await asyncpg.create_pool(dsn)
    try:
        yield pool
    finally:
        await pool.close()

# CORRECT - the root enters the library's own
async def main() -> None:
    settings = Settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        await serve_soundings(pool=pool)
```

### An example is written against its own contracts, never a library's API

**Why:** the model copies examples, the surface included: a unit of work shown in eight skills and
an `AsyncSession` in the caching skill taught one storage design to every task that touched a cache,
a stream or a route. Each skill's examples run against contracts in its own domain - a
`KeeperRoster`, a `BeaconLog` - so they hold whatever library serves them, and a library's own
calls come from its current documentation. `scripts/check_rules.py` reports the
API of the libraries it knows inside any example.

**Example:**
```python
# WRONG - the skill's example is written in SQLAlchemy
@final
class KeeperLookup:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

# CORRECT - the skill's example knows only its own contracts
@final
class KeeperLookup:
    def __init__(self, *, keepers: KeeperRoster) -> None:
        self._keepers = keepers
```

## Descriptions

### A description is what the skill does, `ALWAYS invoke this skill when` and the signals, then `Do not ... directly`

**Why:** the `description` is all the model sees of a skill until it loads it, and a skill it
judges optional it skips. In a 650-trial test the directive form activated every time; a passive
"Use when ..." left the choice to the model
([source](https://medium.com/@ivan.seleznov1/why-claude-code-skills-dont-activate-and-how-to-fix-it-86f679409af1)).
The signals are words a task contains - "one-off", "Authorization header", "environment
variables" - never the rules the skill holds, which no task names. The checker caps it at 400
characters.

**Example:**
```yaml
# WRONG - a table of contents, a passive trigger, and the signals are the skill's own words
description: >-
  Covers composition roots, scopes, resource lifetime, settings and constants. Use when relevant
  to construction.

# CORRECT - what it does, the signals a task contains, and the instruction not to go around it
description: >-
  Designs construction and configuration: one composition root, resource lifetime, settings.
  ALWAYS invoke this skill when a task writes an entry point or main(), opens a pool or a client,
  or reads environment variables. Do not wire objects directly.
```

### Neighbouring descriptions are told apart in their own words

**Why:** the listing is read as a whole, and a description that matches better than the right one
wins - on a public benchmark, wrong selection grew with the library and caused most of the loss.
Two skills whose descriptions both match the same work load the same text twice. Each
names the signals only it should answer - an outbound call for boundaries, an `Authorization`
header for security, a script run once for scripts - and where a neighbour still matches the same
words, a closing `Not for ... (python-x).` names it for the near miss.

## Evaluation

### A rule earns its place by something the model would not do unprompted

**Why:** general practice the model already follows - `pathlib` over `os.path`, a large body
streamed instead of built - costs tokens in every session that loads it and dilutes the rules beside
it. What earns a place is a measured fact, a library's trap, a decision this project made, or the
correction of a default the model gets wrong; and a rule homed elsewhere is not written twice.
Anthropic's guidance asks it of every paragraph: does it justify its token cost?

### A rule is tested with a realistic task that never mentions it, without the rule first

**Why:** a rule is a hypothesis that the model behaves differently with it. Run the task in a fresh
session without the rule and with it, a few times each, and read the code against the rule; a rule
whose task passes without it restates the default and is deleted. The task is seeded with a file to
read, since path-scoped rules arrive on a read, and asks nothing that outranks the rule - "make
sure it is well documented" overrides any rule about comments. The cases live in `evals/python/`;
`evals/run.py --arm both` runs both arms and checks skills invoked, files read, code written.

### A rule leaves a skill's body only after its case passes without it there

**Why:** the model follows what is in its context and copies the example it sees. Deduplicated into a pointer to `principles.md`, the
semaphore left the async skill's body and the bounded fan-out went from passing to one run in
three; with the server's settings shown as one class in the web framework's skill, the split in
`python-wiring` stopped arriving. A move, a merge or a cut runs the rule's case before and after, a
few times each, against the commit the change starts from; a rule that loses there keeps a line and
its `CORRECT` in the body it left.

