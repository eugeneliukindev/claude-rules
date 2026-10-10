---
name: python-rules-authoring
description: >-
  Conventions for writing and auditing the Python coding rules in .claude/rules/python/*.md and
  the python-* skills: stating a rule over its widest category, carve-outs beside prohibitions,
  WRONG/CORRECT pairs that differ in one dimension and obey every other rule, examples that name no
  project, one home per rule, rationed emphasis, skill descriptions as triggers, what loads when,
  the line budget for the always-loaded rules, and testing that a rule changes behaviour.
  Use when editing, adding to, splitting, auditing or evaluating these rule files and skills.
paths:
  - "**/rules/python/**"
  - "**/skills/python-*/**"
---

# Writing These Rules

## How a Rule Is Written

These files are read while writing code, under time pressure, by someone already holding a
different problem in their head. A rule that is technically correct and easy to misread will be
misread. The conventions below prevent that; a rule breaking one of them is a defect **in this
document**, fixed here rather than worked around in code.

**Stated over the widest category it is true for.** A rule written about a class gets applied to
classes and to nothing else — the reader cannot tell whether the other kinds were excluded
deliberately or never considered. Name every kind the rule covers — class, function, constant, type
alias, parameter, module — and let the examples illustrate, never define. The encapsulation rule
said "class" for months, and the cost was twenty-eight public names nobody imports.

**Every prohibition carries its carve-out in the same place.** "Never name a vendor" and
"implementations are named for what makes them concrete" are both true, and a reader who meets the
first without the second renames `SlackNotifier`. An exception three sections away does not exist.

**Every non-obvious rule says what breaks, and when.** "Names are local" is an opinion; "the model
was replaced twice and the name outlived both" is a cost with a date on it. The failure mode is
what lets a reader settle an edge case alone, and what makes the rule survive an argument with
someone in a hurry.

**Examples come in pairs: one invented, one real.** The invented pair — `# WRONG` next to
`# CORRECT` — shows the shape. The real one shows the price, which no invented example can: an
incident that actually happened, concrete enough that the failure can be pictured, told in one
sentence beside the pair. Keep both where a real incident exists; never invent one to fill the
slot — an invented incident teaches a failure nobody has seen.

**The model copies the example, not the prose.** Three consequences, each found in these files by
audits that turned up examples teaching the opposite of the rule above them
([history.md](history.md)):

- **The pair differs in exactly the dimension the rule is about.** Same signature, same names, same
  surrounding code — a `WRONG` that also lacks annotations, uses a global and swallows an error
  leaves the reader guessing which of the eight differences was the point, and they copy all eight.
- **A `CORRECT` obeys every other rule in these files** — `kw_only`, `@override`, `Final`, the `_`
  prefix, units in names, injected dependencies, one-line comments. Where a rule and an example
  disagree, the model has two instructions and picks one arbitrarily.
- **A `CORRECT` is real code**: it parses, it passes `mypy --strict`, and its library calls exist in
  the version the skill names. Run it before committing — `def f(...)` is a syntax error, and an
  API claim from memory is how a skill came to say `orjson` serialises `Decimal`.

**A rule says whether it holds in a script.** These files are written for code that lives, and the
model applies them to a forty-line one-off as readily as to a service. `python-scripts` lists what
relaxes there and what never does; a new rule that would be ceremony in a script joins the first
list in the same change, and one that protects data, money or a credential joins the second.

**Both halves travel, which means neither names a project.** These files are read in every
repository, and a reader who has to know one codebase to understand an example learns nothing from
it — the local proper noun is noise to everyone else and rots the moment that code changes.
So: no domain entity from the project at hand, no vendor, service or model it happens to use, no
identifier copied out of it. Keep the **shape** of the incident and drop its names — "a native
library refuses to write its output file and reports only an exit code" carries the whole lesson,
where the library's name carried none of it. Domain vocabulary in examples stays deliberately
boring and universal: orders, users, notifications, repositories.

## What Holds These Rules Up

Three different things, and the difference matters most when a check passes:

- **The tools** decide syntax, imports, formatting, type errors and mechanical complexity. A green
  check means exactly that much and nothing else.
- **The type checker** decides what survives a rename, a narrowed union, a moved field. This is why
  `Any`, a stringly-typed dict and a silent `getattr` cost far more than the line they sit on.
- **Everything else rests on attention** — every rule here that no tool runs: the encapsulation
  test, the relocation test for names, one actor per module, the extraction tests, the layer
  intent. Nothing fails when they are skipped, and they are skipped first under pressure.

A rule in the third group that is broken in bulk is not a standard, it is a wish. Two honest
outcomes: write the check and move it into the first group, or delete it from this document. Run
that audit whenever violations turn up by the dozen — a rule nobody has followed for months was
never holding anything up. Between the two sits a procedure: the Definition of Done in `core.md` is
eight such rules, and `python-review` walks them over a diff, so they are run on purpose rather
than remembered. A rule that belongs on that list and is missing from it is added to both.

## What Loads When

Two mechanisms, and which one a file lives in is the decision:

| | rule, `paths:` in front matter | rule, no front matter | skill |
|---|---|---|---|
| lives in | `~/.claude/rules/` | `~/.claude/rules/` | `~/.claude/skills/<name>/SKILL.md` |
| enters context | when a matching file is read | at launch, every session, every language | listed once a file matching its `paths` is read or written; loaded when its `description` matches the work, or by `/name` |
| always costs | nothing | its whole length | its `description`, ~40 tokens, and only after `paths` match |

**A rule with no front matter is the expensive one, and it is the easy mistake**: it is the
documented instruction to load the file into every session in every language. That once happened to
sixteen reference files at once, and nothing noticed ([history.md](history.md)).

So: what applies to every edit carries `paths: "**/*.py"`, one topic per file — `core.md`,
`naming.md`, `functions.md`, `control-flow.md`, `classes.md`, `modules.md`, `types.md`,
`errors.md`, `logging.md`, `comments.md` — and all of them load together on the first read;
`testing.md` carries its own test-file globs. Splitting by topic changes the organisation, not the
cost: the same text arrives at the same moment.

**A skill splits when its halves have different triggers and do not need each other.** Then the
work loads only the half it reaches: `python-alembic` arrives with `import alembic`, and a migration
plan does not pull in transaction design. Halves that one task needs together stay one skill —
"pass fields, not the settings object" is a rule about the composition root, and split away from it
it loads without the rule it depends on. Every split costs a description in every session and a row
in the map, which the always-loaded budget pays for. An "and" in a title is a prompt to ask the
question, not the answer. Always-loaded rule files load together whatever their split, so they
split only to give a rule its own address — `logging.md` for what other files point at.
Everything reached by a task rather than by a file — every topic, every library — is a skill, and
`core.md` names every one of them.

**Every skill carries `paths`, so a session lists only the skills of its language.** Without it
every description sits in every session's listing — the Go skills in a Python repository — and a
larger listing costs twice: a description matching better than the right one displaces it, and
past the listing's budget descriptions are dropped. Measured on Claude Code 2.1.118: a skill with
`paths: "**/*.py"` is absent from the listing, and `Unknown skill` when called, until a `.py` file
is read *or written*; the first write in an empty directory therefore happens without it, which is
what `new-files.md` covers. The default is `**/*.py` and `**/pyproject.toml`; a skill whose work
lives in other files adds them — `python-container` the Dockerfile and compose files,
`python-grpc` `**/*.proto`, `python-migrations` and `python-alembic` `**/alembic.ini` — and
`python-rules-authoring` lists only these rule and skill files. `/name` works whatever `paths` says.

**The one file with no front matter is `new-files.md`, six lines, and the exception is
measured.** A path-scoped rule loads when a matching file is *read*; a task that writes `x.py` into
an empty directory reads nothing, and in measured runs such tasks went without the rules. The six
lines cost every session in every language; they buy the rules for the one case the glob cannot
see.

**Tool configuration is not written down here, with one exception.** Which linters a project runs,
what it selects and how its hooks are wired changes from repository to repository, and the person
who owns the repository owns those files. What belongs here is what survives the choice of tool:
the discipline around suppressions and limits, and — where a rule can be handed to a checker
instead of remembered — the name of the check that does it. The exception is `python-project`,
which writes the defaults for an empty directory, where nobody has chosen yet; in an existing
repository the owner's files win.

**Moving a rule up costs every edit; moving it down costs a lookup.** A rule earns a place in the
always-loaded set by being both **universal** — every Python file could break it — and
**behaviour-changing**: without it the obvious default is wrong. A rule that only some paths reach
(async, migrations, a CLI, a shipped example) is a skill, and the map gets a row saying when it
applies. A rule that restates what the model already does by default is deleted, not moved: it
costs attention on every edit and buys nothing.

**A skill loads only when the work names its topic, so universal practice stays in the always-loaded
rules with its examples.** The model looks up `sqlalchemy`, retries or a subprocess when the task
contains them, and never looks up "how to write a function": with the examples for functions,
classes, errors and comments moved into skills, the measured layout lost almost every run and none
of those skills was opened ([history.md](history.md)). What moves to a skill is what a concrete
signal in the task points at — a library, `async def`, a migration, an untrusted input.

**The always-loaded set has a budget, and it is a hard number**, counted from the line after the
front matter's closing `---` — the blank line included, because the model receives it:

| file | ceiling |
|---|---|
| `naming.md` | 300 |
| any other rule file | 120 |
| **everything loaded on every `.py`** | **800** |
| any one `SKILL.md` | 500 |

The number is not sacred; the *fixedness* is. Without one, every addition looks free — each is a
paragraph, and the file once grew to three thousand lines one paragraph at a time. With one, **an
addition displaces something**: find the rule it makes redundant, the example that has stopped
earning its lines, or the section that belongs in a skill, and cut that first. If nothing can be
cut, the new rule was not worth the space, and it becomes a skill with a row in the map. How the
numbers were set is in [history.md](history.md).

The 500-line ceiling on a `SKILL.md` is not this project's invention — it is what Anthropic's
authoring guidance asks for, and past it a skill splits into reference files linked from
`SKILL.md`, **one level deep and no further**: a file reached through another file gets read in
fragments, `head -100` at a time, and the rule at line 200 silently does not arrive. A reference
file past a hundred lines opens with its own table of contents for the same reason.

Raising the ceiling is allowed exactly once per good argument, written down in
[history.md](history.md) with the arithmetic — never because the file happens to have grown past
it. A ceiling adjusted to fit the current size is not a ceiling.

**Prefer the positive.** Steering by prohibition backfires — naming the thing to avoid makes it
more available, not less. Where a positive statement exists, lead with it and let the `# WRONG`
example carry the negative. Keep a bare `NEVER` for the rules where the wrong answer is genuinely
tempting and the right one is not obvious from the positive alone.

**Emphasis is rationed, and the reason does the work.** Current models follow instructions closely,
and capitals make them over-apply a rule to cases it was never meant for; a file where every second
line says `MUST` has no emphasis left for the one rule that keeps being skipped. State the rule
plainly with its reason — the model generalises from the reason — and bold the rule's name, not
its modality.

## Checked, Not Remembered

A budget counted by eye was broken by six lines before anyone noticed. What this file can hand to a
machine, `scripts/check_rules.py` checks: the budget, that every `python` block parses, that every
skill and `.md` file a document names exists, that `core.md` names every skill, and that every
`SKILL.md` has a `name` matching its directory, a `description` and `paths`.

```bash
python <this skill's directory>/scripts/check_rules.py ~/.claude
```

Point it at `.claude` in a clone of the rules. Run it before every commit to these files; exit code
1 means a finding, printed as `path:line: message`. What it cannot check stays a step of its own:
that a `CORRECT` passes `mypy --strict` and runs against its library at the version the skill
names — paste the block into a file with the names it uses declared, and run both.

## One Rule, One Home

**A rule is written in exactly one file, and every other file points to it.** Three copies of the
retry policy drift into three policies; two files that disagree about where a test fake lives get
one of them followed at random.

**A topic skill is library-agnostic; a library with traps of its own is a skill of its own.** The
topic's examples run against the application's own contract — a `Cache`, a `TokenVerifier`, an
`OrderEventChannel` — and the library skill implements that contract and adds the library's traps:
`python-caching` and `python-redis`, `python-persistence` and `python-sqlalchemy`. A library that
earns a line or a table row, not a screen, stays in the topic as that line.

**A skill is self-sufficient at its trigger, and a pointer adds depth, never the rule.** Naming a
skill does not load it — Anthropic's own guidance says skills cannot reference each other, and the
model decides what to open. So a skill that relies on a rule homed elsewhere states it as **one
imperative line** and points home for the reason, the examples and the carve-outs: "a cache failure
is a counted miss, never an error (why and how: `python-caching`)". One line is the ceiling; the
reasoning stays in one file and cannot drift.

**A carve-out lives beside its prohibition, even across files.** "Retry only in the adapter" in one
skill and "a deadlock retries the whole unit of work" in another are two contradictory rules until
each file states the exception in the same place as the rule.

## A Skill's Description Is Its Trigger

The `description` is all the model sees of a skill until it decides to load it, among a few dozen
others. It is written in the third person, says **what** the skill covers and then **when** to use
it, and puts the words a user or a file would actually contain first — library names, `async def`,
"slow", "migration" — because the listing is truncated from the end. A skill that never loads
teaches nothing; two skills whose descriptions both match the same work load the same text twice.

**Neighbouring descriptions are told apart in their own words.** The listing is read as a whole,
and a description that matches better than the right one wins — on a public benchmark, wrong
selection grew with the size of the library and caused most of the loss. A topic says it holds the
design "whatever the library" and names its library skills; a library skill starts with the
library's name and says the design lives in the topic.

## Evaluation Before and After

A rule is a hypothesis that the model behaves differently with it than without it. Test it the way
it will be used: a realistic task that never mentions the rule, run in a fresh session without the
rule and then with it, a few times each, and the produced code read against the rule. Run it
without the rule first, to see that the default actually fails. A rule whose task passes without
it restates what the model already does, and is deleted. Seed the task with a file to read —
path-scoped rules arrive on a read — and keep the prompt free of requests that outrank the rule:
"make sure it is well documented" overrides any rule about comments, by design.
