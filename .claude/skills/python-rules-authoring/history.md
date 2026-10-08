# What Broke, and When

The incidents and measurements behind the conventions in `SKILL.md`. The conventions stand on
their own; this file is the evidence for an argument about changing one of them.

## Loading

**Sixteen reference files once sat in `~/.claude/rules/` with no `paths:`**, which is the
documented instruction to load every one of them into every session in every language — eighteen
hundred lines — while the pair that actually governed each edit waited on a glob. The prose in the
authoring guide described the opposite arrangement for months and nothing contradicted it, because
nothing checks a claim about loading.

**`new-files.md` exists because of a measurement.** A path-scoped rule loads when a matching file
is *read*; a task that writes `x.py` into an empty directory reads nothing. In measured runs every
such task went without the rules: the dataclass scenario passed three of three with a file to read
first, and none of three without.

**Universal practice stays in the always-loaded rules, with its examples.** A variant that left
one-line rules in `core.md` and moved the examples for functions, classes, errors and comments into
four skills lost to the current layout in 38 to 42 of 42 runs, and none of the four skills was
opened once: the model looks up `sqlalchemy`, retries or a subprocess when the task contains them,
and never looks up "how to write a function". The actor rule was the clearest case — with the
example in `core.md` the model split pay and hours into two modules three times out of three; with
the example one skill away it never did.

## The Budget

**The ceilings were lowered from 600 + 350 once**, with this arithmetic: Anthropic asks for under
200 lines in an always-loaded instruction file because adherence falls as the file grows, and 950
lines were about twelve thousand tokens on every Python edit. An audit then found the contract
sections, the resource lifecycle, dunders and the stdlib-shadowing rule reached only by some work —
they became skill content — and a dozen rules the model follows without being told, which were
deleted. What remained was 800 lines; the ceiling was set there so the next addition would have to
displace something. `core.md` was then split by topic with its text unchanged.

**Without a fixed number the file grew from 350 lines to three thousand**, one paragraph at a time,
each addition looking free.

**The budget was then broken by six lines, and `core.md` by one, with nobody noticing** — counted by
eye, after the always-loaded set had reached 806. That is why the count is now a script
(`scripts/check_rules.py`), and why the blank line after the front matter is counted: the model
receives it.

## Examples

**An audit found a dozen examples teaching the opposite of the rule above them** — a `WRONG` that
differed from its `CORRECT` in five ways, a `CORRECT` missing `kw_only` or `@override`. The next
review found two more: implementations in `classes.md` and `naming.md` without `@final`, and one
without `@override`.

**An API claim from memory** is how a skill came to say `orjson` serialises `Decimal`; it raises
`TypeError`.

## Reproducing the Measurements

The runs above were made outside the repository, which keeps only what a user of the rules needs.
Each one followed **Evaluation Before and After** in `SKILL.md`: a realistic task that never
mentions the rule, a file to read first, a fresh session without the rule and then with it, a few
runs each, the produced code read against the rule. To repeat one, rebuild its task from the
description here — the scenario, the file it reads, the behaviour counted — and run both arms
again; a number that does not reproduce is removed from this file.
