# What Broke, and When

The incidents and measurements behind the conventions in the `python-rules-authoring` skill. The conventions stand on
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

**The line ceiling was replaced by a rule count and a token count once**, when every rule moved to
one heading, a `**Why:**` and an `**Example:**`. That shape costs about twenty-five tokens of markup
per rule and no instructions, and lines would have charged it like new rules. The arithmetic:
IFScale (2025, twenty models, up to 500 simultaneous instructions) found adherence starting to fall
around 150 to 200 instructions, and Claude Code's own system prompt spends about fifty; the
always-loaded set held about 126 rules and checklist items, 790 lines and 12,500 tokens. So 120
rules — the headroom below that band — and 16,000 tokens, the 12,500 plus the markup for every rule
and room for the examples it frees. Anthropic's under-200-lines figure for an always-loaded file
became the per-file ceiling, which split the naming rules into two files; once the budget counted
the set, the split files were merged back.

**The token ceiling was raised from 16,000 to 28,000 once**, when every example became complete
code — the `class` statement, its fields and real bodies — instead of a fragment. Three files in the
new shape — classes, SOLID and modules — took the set from 12,600 to 16,000 tokens with
nine files still to go; the converted files had grown about 2.3 times. 28,000 is that rate applied
to the rest, with the rule ceiling of 120 unchanged: examples are tokens, not instructions, and the
instruction count is what the adherence studies measured.

**The per-file line ceiling for rules was replaced by a budget for the test-file set once**, when
`testing.md` in the new shape reached 494 lines and was split into three files to fit 200. The three
carried the same test-file globs and loaded together, so the split changed the organisation and
not one token of the cost; it was merged back. The 200 lines are Anthropic's figure for one
always-loaded CLAUDE file, where file and set coincide; for rules that load together the set is
what the model receives. A test file loaded 111 rules and about 29,000 tokens: the every-`.py`
ceilings plus twenty rules and 8,000 tokens for `testing.md` give 140 and 36,000, still below the
150-instruction band where adherence starts to fall.

**A `SKILL.md` gained a token ceiling of 5,000 at the same time.** The Agent Skills specification
recommends it, and Claude Code re-attaches only the first 5,000 tokens of each invoked skill after
compaction. Seven skills were already past it; they are listed in the checker and leave the list
as they are converted, with material moved to reference files inside the same skill. Third-party
skills measured on the same day ran from 1,200 to 3,100 tokens in the body, the larger ones (the
official `fastapi` skill, `playwright-cli`) with six to nine reference files beside it.

**The budget was then broken by six lines, and `core.md` by one, with nobody noticing** — counted by
eye, after the always-loaded set had reached 806. That is why the count is now a script
(`scripts/check_rules.py`), and why the blank line after the front matter is counted: the model
receives it.

**The ceilings came down to 100 rules and 22,000 tokens, and 120 and 28,000 on a test file**, after
a comparison with public skill collections — Claude Code's own guidance asks for under 200 lines in
an always-loaded file, and the largest Go collection keeps everything loaded at once near 10,000
tokens. The set then stood at 95 rules and 22,800 tokens. A duplicate of `python-contracts`' rule on
`Protocol`, the two contract rules a subclass or a consumer's parameter signals, logging
configuration, the environment-name rule, the naming self-check that restated its own file and a
second pair beside the actor rule left it, for 90 rules and 20,500 tokens; the new ceilings are that
plus headroom. Little of it was a tool's to decide — `core.md` already kept style out — so a deeper
cut means fewer examples, the layout measured above that lost 38 to 42 of 42 runs.

**The `SKILL.md` line ceiling came down from 500 to 300 once.** A body line in these skills averages
about 10.5 tokens, so 500 lines were about 5,250 tokens — past the 5,000 Claude Code re-attaches
after compaction, which a long skill lost its end to — and 300 lines are about 3,150, below it with
room for code lines longer than the average. Three skills were longer at the time; each moved a
branch into a reference file.

**Reference files were inlined, and the ceiling went to 500 lines and 6,000 tokens, by the user's
decision.** The model opens a linked file in a minority of runs — in the evals the integration file
was read in one or two runs of eight — so a branch moved out was a branch most runs never saw, and a
separate skill would compete for invocation instead. Every skill is now one `SKILL.md` with no links
to other `.md` files; what does not fit is cut, not moved. 6,000 tokens is past the 5,000 Claude
Code re-attaches after compaction by a short tail, the price of one file; the checker reports any
other `.md` file in a skill, and this history moved out of the skills to `docs/`.

## Skills Taught Each Other

**`managed_*` was one skill's convention that every library skill copied.** `python-wiring` named a
resource's context manager for its lifetime — `managed_pool` — and the library skills each wrapped
their library the same way: `managed_redis`, `managed_cashews`, `managed_grpc_server`,
`managed_carrier_session`. The model learned the prefix and wrote wrappers around libraries whose
own `with` already did the job. The checker's factory pattern lost the prefix, a lifetime is now
recognised by its `@contextmanager` decorator, and a library skill enters the library's own context
manager.

**An audit of every skill against the rules found 273 findings at the start**: 136 references to a
neighbour skill outside an introduction, about 130 names shared between skills or between a skill
and the rules, three `SKILL.md` past 300 lines, and two settings read inside a factory. Behind the
shared names were domains leaking across skills — the broker and the consumer skills both on room
inventory, the cache, cashews and redis skills all on profiles — and behind the references, rules
homed twice: a rule file and a skill stating the same idempotency rule, the same constructor rule,
the same `Any` rule. Every skill was rewritten in a domain of its own, the duplicates kept one home,
and the checker learned the shared-name and the introduction-only checks; the comparison point for
the evals is the commit before the rewrite, `10cdec7`.

**A setting became a defaulted keyword parameter in every function, by the user's decision.** The
rule had covered only a factory and a class the root builds, and inside an ordinary function a
constant stayed; the examples then disagreed with one another about the same timeout. A default
costs the caller nothing, a test passes its own value, and it is the same injection the
constructor rule asks for, so the rule was widened to every function and method, with the root,
tests, fixtures, framework-parsed signatures, decorator arguments, format and protocol values and
one-off scripts excepted. Forty examples broke it on the day; the checker reports each.

## Examples

**An audit found a dozen examples teaching the opposite of the rule above them** — a `WRONG` that
differed from its `CORRECT` in five ways, a `CORRECT` missing `kw_only` or `@override`. The next
review found two more: implementations in `classes.md` and `naming.md` without `@final`, and one
without `@override`.

**An API claim from memory** is how a skill came to say `orjson` serialises `Decimal`; it raises
`TypeError`.

## The Skill Set

**Forty skills became eight, by the user's decision.** The always-loaded core stays, and
eight skills keep the design only some work reaches — types, contracts, wiring, boundaries,
security with authentication folded in, scripts, review and this one. The fifteen library skills
and `python-integrations/` were deleted, with the topic skills only their neighbours needed: a
library's API moves with every release, faster than these files were checked, and the one claim
written from memory that was caught — `orjson` and `Decimal` — had shipped. A library's traps now
come from its current documentation, fetched at the time (context7), and from the tests run
against it; the checker still keeps library APIs out of every example.

**Descriptions moved from "Use when …" to "ALWAYS invoke this skill when …" at the same time.** A
650-trial test of skill descriptions found the directive form — what the skill does, "ALWAYS invoke
this skill when" the signals, "Do not … directly" — the one that activated every time
([source](https://medium.com/@ivan.seleznov1/why-claude-code-skills-dont-activate-and-how-to-fix-it-86f679409af1));
the checker's required clause changed with it.

**`python-types` became part of `types.md`, by the user's decision.** Typing applies to every
Python file, and a skill is invoked only when its description matches the task, so its rules
reached only the work that named a type. The skill was merged into the always-loaded file, its
duplicate rules folded into one and the examples the model gets right without them dropped; the
every-`.py` set went from 42 rules and about 8,960 tokens to 55 and about 12,370.

**A rule's prose got a ceiling of 700 characters, aim 600, by the user's decision** — rules had
grown to 1,400 by accreting clauses; cutting them took the every-`.py` set from about 12,450 tokens
to about 11,660.

## Reproducing the Measurements

The runs above were made outside the repository, which keeps only what a user of the rules needs.
Each one followed the evaluation test in `python-rules-authoring`: a realistic task that never
mentions the rule, a file to read first, a fresh session without the rule and then with it, a few
runs each, the produced code read against the rule. To repeat one, rebuild its task from the
description here — the scenario, the file it reads, the behaviour counted — and run both arms
again; a number that does not reproduce is removed from this file.
