# Writing These Rules

Not loaded automatically — open it when editing the rule files themselves.

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

Only `core.md` and `naming.md` carry `paths: "**/*.py"`, because only they apply to every edit.
`testing.md` carries its own test-file globs. Everything else — this file, `topics/`, `libraries/`
— has no front matter and is opened deliberately, from the map at the top of `core.md`.

**Tool configuration is not written down here at all.** Which linters a project runs, what it
selects, what it excludes and how its hooks are wired changes from repository to repository, and
the person who owns the repository owns those files. What belongs here is only what survives the
choice of tool: the discipline around suppressions and limits, and — where a rule in these files
can be handed to a checker instead of remembered — the name of the check that does it.

**Moving a rule up costs every edit; moving it down costs a lookup.** A rule earns a place in the
always-loaded pair by being both **universal** — every Python file could break it — and
**behaviour-changing**: without it the obvious default is wrong. A rule that only some paths reach
(async, migrations, a CLI, a shipped example) goes to `topics/`, and the map gets a row saying when
to open it. A rule that restates what the model already does by default is deleted, not moved: it
costs attention on every edit and buys nothing.

**The always-loaded pair has a budget, and it is a hard number:**

| file | ceiling |
|---|---|
| `core.md` | 600 |
| `naming.md` | 350 |
| **always loaded** | **950** |

The number is not sacred; the *fixedness* is. Without one, every addition looks free — each is a
paragraph, and the file went from 350 lines to three thousand one paragraph at a time. With one,
**an addition displaces something**: find the rule it makes redundant, the example that has stopped
earning its lines, or the section that belongs in `topics/`, and cut that first. If nothing can be
cut, the new rule was not worth the space, and it goes to `topics/` with a row in the map.

Raising the ceiling is allowed exactly once per good argument, written down here with the
arithmetic — never because the file happens to have grown past it. A ceiling adjusted to fit the
current size is not a ceiling.

**Prefer the positive.** Steering by prohibition backfires — naming the thing to avoid makes it
more available, not less. Where a positive statement exists, lead with it and let the `# WRONG`
example carry the negative. Keep a bare `NEVER` for the rules where the wrong answer is genuinely
tempting and the right one is not obvious from the positive alone.
