# Where a Rule Lives

## Contents

- What loads when
- What applies to every edit carries `paths: "**/*.py"`
- `new-files.md`, the one file with no front matter
- Every skill carries `paths`
- The always-loaded set: universal and behaviour-changing, with its examples
- Tool configuration belongs to the repository
- The budget, and ceilings raised only by argument
- A skill grows by a reference file per branch
- What tools cannot check becomes a check, or goes

Two mechanisms, and which one a file lives in is the decision:

| | rule, `paths:` in front matter | rule, no front matter | skill |
|---|---|---|---|
| lives in | `~/.claude/rules/` | `~/.claude/rules/` | `~/.claude/skills/<name>/SKILL.md` |
| enters context | when a matching file is read | at launch, every session, every language | listed once a file matching its `paths` is read or written; loaded when its `description` matches the work, or by `/name` |
| always costs | nothing | its whole length | its `description`, and only after `paths` match |

The always-loaded set has a hard budget, counted in what costs adherence — instruction-following
falls as the number of instructions grows, and an example is tokens but not an instruction:

| what | ceiling |
|---|---|
| **rules loaded on every `.py`** — `###` headings, or top-level bold bullets in a file not yet in that format | **120** |
| **tokens loaded on every `.py`**, estimated at four characters each | **28,000** |
| rules loaded on a test file — the set above plus `testing.md` | 140 |
| tokens loaded on a test file | 36,000 |
| lines in any one `SKILL.md`, after the front matter | 500 |
| tokens in any one `SKILL.md`, after the front matter | 5,000 |

The 500 lines are what Anthropic's authoring guidance and the Agent Skills specification ask for;
5,000 tokens is the specification's figure and the part of an invoked skill Claude Code re-attaches
after compaction — past it, the end of the skill is gone for the rest of the session.

### What applies to every edit is a rule file with `paths: "**/*.py"`, one topic per file

**Why:** a rule with no front matter is the documented instruction to load it into every session in
every language, and it is the easy mistake: sixteen reference files once sat there at once, and
nothing noticed. The always-loaded files — `core.md`, `naming.md`, `types.md` and the rest — load
together on the first read, `testing.md` on its own test-file globs; splitting them by topic changes
the organisation, not the cost, so one splits only to give a rule its own address.

### `new-files.md` is the one file with no front matter, and the exception is measured

**Why:** a path-scoped rule loads when a matching file is *read*; a task that writes `x.py` into an
empty directory reads nothing, and in measured runs such tasks went without the rules. Its six lines
cost every session in every language; they buy the rules for the one case the glob cannot see.

### Every skill carries `paths`, so a session lists only the skills of its language

**Why:** without it every description sits in every session's listing — the Go skills in a Python
repository — where a better-matching wrong description displaces the right one, and past the
listing's budget descriptions are dropped. Measured on Claude Code 2.1.118: a skill with
`paths: "**/*.py"` is absent from the listing, and `Unknown skill` when called, until a `.py` file
is read *or written*. The default is `**/*.py` and `**/pyproject.toml`; a skill whose work lives in
other files adds them, and `/name` works whatever `paths` says.

**Example:**
```yaml
# WRONG — no paths: listed in every session, in every language
name: python-grpc
description: ...

# CORRECT — listed once Python or a .proto file is touched
name: python-grpc
description: ...
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/*.proto"
```

### The always-loaded set holds what is universal and behaviour-changing, with its examples

**Why:** every edit pays for an always-loaded rule, so it earns that by being universal — every
Python file could break it — and behaviour-changing — without it the obvious default is wrong. A
rule only some paths reach (async, migrations, a CLI) is a skill with a row in the map. But a skill
loads only when the work names its topic: with the examples for functions, classes, errors and
comments moved into skills, the measured layout lost almost every run and none of those skills was
opened. What moves to a skill is what a concrete signal in the task points at — a library,
`async def`, a migration, an untrusted input.

### Tool configuration belongs to the repository; the rules hold what survives the choice of tool

**Why:** which linters a project runs and how its hooks are wired changes from repository to
repository, and its owner owns those files. What belongs here is the discipline around suppressions
and limits and, where a checker can hold a rule, the name of the check. The exception is
`python-project`, which writes the defaults for an empty directory where nobody has chosen yet.

### An addition displaces something, and a ceiling is raised only by an argument on record

**Why:** without a fixed number every addition looks free, and a file once grew to three thousand
lines one paragraph at a time. A new rule finds what it makes redundant, the example that has
stopped earning its tokens, or the section that belongs in a skill, and cuts that first; if nothing
can be cut, it becomes a skill. The budget counts the set, not the file. Raising a ceiling is
allowed once per good argument, written into `history.md` with the arithmetic — a ceiling adjusted
to fit the current size is not a ceiling.

### A skill grows by a reference file per branch, never by a second skill for the same trigger

**Why:** Anthropic's guidance organises a multi-domain skill as one skill with a reference file per
domain, and every extra skill puts another description into a listing Claude Code caps at 1% of the
context window, dropping the least-invoked first. A second skill is for a second trigger: halves
that one task needs together stay one skill. The body is the router — it keeps what every task
under the trigger needs, and each branch, a kind of work only some tasks reach, is one reference
file however few rules it holds. At the place the branch belongs, a section names the code that
reaches it, because the wording of a pointer decides whether it fires, and what the file holds; the
body carries no second list of the files. References go one level deep: a file reached through
another is read in fragments, and the rule at line 200 does not arrive. A reference file past a
hundred lines opens with its own table of contents.

**Example:**
````markdown
<!-- WRONG — a list of files at the top, and a topic instead of the code that reaches it -->
See also: [time.md](time.md), [money.md](money.md), [identifiers.md](identifiers.md).

<!-- CORRECT — a section where the branch belongs, conditioned on code -->
## Time

**Before writing code that creates, compares, stores or serializes a `datetime`, measures a
deadline or holds a duration, read [time.md](time.md)** — aware UTC, offsets required at the edge,
arithmetic in UTC, the injected clock, monotonic deadlines.
````

### A rule no tool checks either becomes a check or is deleted, once it is broken in bulk

**Why:** the tools decide syntax, imports and formatting; the type checker decides what survives a
rename; everything else rests on attention, and nothing fails when it is skipped. A rule broken by
the dozen is a wish, not a standard: write the check, or delete the rule. Between the two sits a
procedure — the Definition of Done in `core.md`, which `python-review` walks over a diff — and a
rule that belongs on that list is added to both.
