---
name: python-rules-authoring
description: >-
  Conventions for writing the Python rule files and skills in this collection: stating a rule over
  the widest category it is true for, carve-outs beside prohibitions, naming what breaks and when,
  paired invented and real examples, examples that name no project, what the tools hold versus
  what rests on attention, what loads when, and the line budget for the always-loaded rules. Use
  when editing, adding to, splitting or auditing these Python rule files and skills.
---

# Writing These Rules

## How a Rule Is Written

These files are read while writing code, under time pressure, by someone already holding a
different problem in their head. A rule that is technically correct and easy to misread will be
misread. Four conventions prevent that; a rule breaking one of them is a defect **in this
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
incident that actually happened, concrete enough that the failure can be pictured. Keep both; drop
either and the rule teaches half of itself.

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
  test, the relocation test for names, one-reason-to-change, the extraction tests, the layer
  intent. Nothing fails when they are skipped, and they are skipped first under pressure.

A rule in the third group that is broken in bulk is not a standard, it is a wish. Two honest
outcomes: write the check and move it into the first group, or delete it from this document. Run
that audit whenever violations turn up by the dozen — a rule nobody has followed for months was
never holding anything up.

## What Loads When

Two mechanisms, and which one a file lives in is the decision:

| | rule, `paths:` in front matter | rule, no front matter | skill |
|---|---|---|---|
| lives in | `~/.claude/rules/` | `~/.claude/rules/` | `~/.claude/skills/<name>/SKILL.md` |
| enters context | when a matching file is read | at launch, every session, every language | when its `description` matches the work, or by `/name` |
| always costs | nothing | its whole length | its `description`, ~40 tokens |

**A rule with no front matter is the expensive one, and it is the easy mistake.** Sixteen
reference files sat in `~/.claude/rules/` with no `paths:`, which is the documented instruction to
load every one of them into every session in every language — eighteen hundred lines, while the
pair that actually governs each edit waited on a glob. The prose in this section described the
opposite arrangement for months and nothing contradicted it, because nothing checks a claim about
loading.

So: `core.md` and `naming.md` carry `paths: "**/*.py"`, because only they apply to every edit;
`testing.md` carries its own test-file globs. Everything reached by a task rather than by a file —
every topic, every library — is a skill, and the map at the top of `core.md` names them.

**Tool configuration is not written down here at all.** Which linters a project runs, what it
selects, what it excludes and how its hooks are wired changes from repository to repository, and
the person who owns the repository owns those files. What belongs here is only what survives the
choice of tool: the discipline around suppressions and limits, and — where a rule in these files
can be handed to a checker instead of remembered — the name of the check that does it.

**Moving a rule up costs every edit; moving it down costs a lookup.** A rule earns a place in the
always-loaded pair by being both **universal** — every Python file could break it — and
**behaviour-changing**: without it the obvious default is wrong. A rule that only some paths reach
(async, migrations, a CLI, a shipped example) is a skill, and the map gets a row saying when it
applies. A rule that restates what the model already does by default is deleted, not moved: it
costs attention on every edit and buys nothing.

**The per-edit pair has a budget, and it is a hard number:**

| file | ceiling |
|---|---|
| `core.md` | 600 |
| `naming.md` | 350 |
| **loaded on every `.py`** | **950** |
| any one `SKILL.md` | 500 |

The number is not sacred; the *fixedness* is. Without one, every addition looks free — each is a
paragraph, and the file went from 350 lines to three thousand one paragraph at a time. With one,
**an addition displaces something**: find the rule it makes redundant, the example that has stopped
earning its lines, or the section that belongs in a skill, and cut that first. If nothing can be
cut, the new rule was not worth the space, and it becomes a skill with a row in the map.

The 500-line ceiling on a `SKILL.md` is not this project's invention — it is what Anthropic's
authoring guidance asks for, and past it a skill splits into reference files linked from
`SKILL.md`, **one level deep and no further**: a file reached through another file gets read in
fragments, `head -100` at a time, and the rule at line 200 silently does not arrive. A reference
file past a hundred lines opens with its own table of contents for the same reason.

Raising the ceiling is allowed exactly once per good argument, written down here with the
arithmetic — never because the file happens to have grown past it. A ceiling adjusted to fit the
current size is not a ceiling.

**Prefer the positive.** Steering by prohibition backfires — naming the thing to avoid makes it
more available, not less. Where a positive statement exists, lead with it and let the `# WRONG`
example carry the negative. Keep a bare `NEVER` for the rules where the wrong answer is genuinely
tempting and the right one is not obvious from the positive alone.
