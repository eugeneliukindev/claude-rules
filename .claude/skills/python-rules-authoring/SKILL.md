---
name: python-rules-authoring
description: >-
  Writes and audits these Python rules and skills: the rule format, examples, one home per rule,
  layering, descriptions, what loads when, budgets. Use when editing, adding, splitting or
  auditing a file under rules/python or a python-* skill.
paths:
  - "**/rules/python/**"
  - "**/skills/python-*/**"
---

# Writing These Rules

These files are read while writing code, under time pressure, by someone already holding a
different problem in their head. A rule that is technically correct and easy to misread will be
misread; a rule breaking one of the conventions below is a defect **in this document**, fixed here
rather than worked around in code. The incidents behind the conventions are in
[history.md](history.md).

### Every rule is a heading and a `**Why:**`, and an `**Example:**` only where it earns its place

**Why:** a fixed hierarchy lets the reader find the part they need without reading the rest, the way
a linter documents a check. The heading is the rule, one sentence, `###` under the topic's `##`. The
`**Why:**` is what breaks, and when — Anthropic's guidance asks for the motivation because the model
generalises from it, and a measured incident goes here in a clause. The `**Example:**` is the pair,
`# WRONG` and `# CORRECT`; a carve-out is one more `# CORRECT`, or one `**Except:**` sentence before
the example when it needs words. An example earns its place when the model gets the code wrong
without it — a library's trap, a measured fact — when the shape of the code is not readable from the
heading — an actor split, a contract suite, guards first — or when its effect was measured. A rule
whose heading already says what the code looks like — `Final` on a constant, the unit in a name —
has none: every example is one more place another rule can contradict, and each is checked against
all of them. Undecided, an always-loaded rule keeps its example and a skill's rule drops it. A list
that *is* the rule — the module order, the Definition of Done — stays a list. Prose beyond that is
cut: an explanation the example already shows, a restatement, the history of the rule.

**Example:**
``````markdown
<!-- WRONG — a bold bullet with the reason and the example scattered around it -->
- **Collaborators arrive through the constructor.** This matters for tests, as discussed in the
  testing section; see the example further down.

<!-- CORRECT — the rule, what breaks, and the pair -->
### Collaborators arrive through the constructor

**Why:** one built inside cannot be replaced in a test, and its signature hides what it needs.

**Example:**
```python
# WRONG — the repository is built inside: no test can hand in a fake
@final
class DocumentArchive:
    def __init__(self, *, engine: AsyncEngine) -> None:
        self._documents = PostgresDocumentRepository(engine)


# CORRECT — it arrives from the composition root
@final
class DocumentArchive:
    def __init__(self, *, documents: DocumentRepository) -> None:
        self._documents = documents
```
``````

### A rule is stated over the widest category it is true for

**Why:** a rule written about a class gets applied to classes and to nothing else — the reader
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

**Why:** the model copies the example, not the prose. A fragment teaches the shape of a fragment — a
bare `def __init__` is copied as readily as a whole class — so a method appears inside its `class`
with the fields and constructor it uses, and a body is the real one wherever the body is the point.
A `WRONG` that also lacks annotations, uses a global and swallows an error leaves eight differences,
and the reader copies all eight. Imports and the declarations of names an example uses are omitted
in every file.

**Example:**
```python
# WRONG — a fragment, and a WRONG that differs from its CORRECT in three ways at once
def __init__(self):
    self.repo = PostgresDocumentRepository(ENGINE)

# CORRECT — the whole class, the way the rule's own pair shows it
@final
class DocumentArchive:
    def __init__(self, *, documents: DocumentRepository) -> None:
        self._documents = documents
```

### A `CORRECT` obeys every other rule here, parses, and passes `mypy --strict`

**Why:** where a rule and an example disagree, the model has two instructions and picks one
arbitrarily — `kw_only`, `@override`, `Final`, the `_` prefix, units in names and injected
dependencies hold in every `CORRECT`. An API claim from memory is how a skill came to say `orjson`
serialises `Decimal`: the block is pasted into a scratch file with its names declared and run
against the library at the version the skill names before it is committed.

### Examples vary their domain, and neither half names a project

**Why:** the model copies the surface too: Anthropic's guidance asks for diverse examples "so Claude
doesn't inadvertently pick up on unintended patterns", one practitioner traced a pattern from 0.3%
of the input to 36% of the output through a single example line, and an audit found 43% of these
files' Python blocks built on orders. One domain holds within a skill whose examples build on each
other, and no domain more than about a sixth of all blocks. These files are read in every
repository, so no entity, vendor or identifier of the project at hand appears — the shape of the
incident carries the lesson, its names carry none of it.

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

**Why:** a budget counted by eye was broken by six lines before anyone noticed. The script checks
the budgets and the `SKILL.md` ceilings, that every `python` block parses, that every skill and
`.md` file a document names exists, that `core.md` names every skill, every front matter and
description, and the layering; exit code 1 means a finding, printed as `path:line: message`. What it
cannot check — that a `CORRECT` passes `mypy --strict` against its library — stays a step of its
own.

## Where a Rule Lives

**Before adding a rule, moving one between files, splitting a skill or adding a reference file,
read [placement.md](placement.md)** — what loads when, `paths` on every skill, the always-loaded
budget and the `SKILL.md` ceilings, a reference file per branch, and what holds a rule up.

## One Rule, One Home

**Before writing a rule another file already touches, or naming a library in a topic skill, read
[layering.md](layering.md)** — one home per rule, topic skills library-agnostic, one imperative
line plus a pointer.

## Descriptions

**Before writing or changing a skill's `description`, read [descriptions.md](descriptions.md)** —
what it does and `Use when` with the signals a task contains, told apart from its neighbours.

## Evaluation

**Before adding a rule or deciding whether one earns its place, read
[evaluation.md](evaluation.md)** — what the model would not do unprompted, and the with-and-without
test.
