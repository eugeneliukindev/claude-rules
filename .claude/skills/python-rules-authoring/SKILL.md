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

These files are read while writing code, under time pressure, by someone holding a different problem in their head; a rule easy to misread will be misread. Treat a rule that breaks a convention below as a defect in this document, and fix it here rather than in code. The incidents behind the conventions are in docs/rules-history.md, evidence for people, not instructions.

## The Rule Format

- **Write every rule as one bullet with a bold imperative lead: the verb phrase in bold, then at most one short reason.** The lead is the rule, verb first, second person implied, under its topic's `##`; the checker counts a rule by its bold lead.
- **Give the reason as what breaks, and when, in plain words.** The model generalises from the motivation, and the reason lets a reader settle an edge case alone; keep explanation, history and incidents out.
- **Fold a carve-out into the bullet it qualifies ("..., unless ..."), never under a label.** An exception three sections away, or in another file, does not exist; a rule and its exception stated apart are two contradictory rules.
- **Keep one rule per bullet, and a bullet at most 500 characters, aim 400.** Past that it is two rules or a lecture.
- **Write no code examples: no fenced blocks, and inline code only for names and spellings.** Every example is one more place another rule can contradict, and the model copies its surface; a list that is the rule, like the module order, stays a list.
- **State a rule over the widest category it is true for, and name every kind it covers.** A rule written about a class gets applied to classes and nothing else, and the reader cannot tell whether the other kinds were excluded deliberately.
- **Lead with the positive, and lead with `Never` only when the positive alone does not make the right answer obvious.** Naming the thing to avoid makes it more available; capitals make a model over-apply a rule, and a file full of `MUST` has no emphasis left.
- **Never name an entity, vendor or identifier of the project at hand.** These files are read in every repository, and the model copies names too.
- **Check every library API claim against the version the skill names before commit.** An API from memory teaches a call that does not exist.
- **Say in a new rule whether it holds in a one-off script.** Add a rule that would be ceremony there to what `python-scripts` relaxes, and one that protects data, money or a credential to what never relaxes, in the same change.
- **Run `scripts/check_rules.py` before every commit, and fix every finding.** It checks the budgets (rules and tokens on every `.py`, each `SKILL.md`'s 500 lines and 6,000 tokens, each rule's 500 characters), front matter and descriptions, that named files and skills exist, where skills name each other, and ASCII punctuation; a finding is `path:line: message`, exit 1.

## Where a Rule Lives

Which mechanism a file lives in is the decision:

| | rule, `paths:` in front matter | rule, no front matter | skill |
|---|---|---|---|
| lives in | `~/.claude/rules/` | `~/.claude/rules/` | `~/.claude/skills/<name>/SKILL.md` |
| enters context | when a matching file is read | at launch, every session, every language | listed once a file matching its `paths` is read or written; loaded when its `description` matches the work, or by `/name` |
| always costs | nothing | its whole length | its `description`, and only after `paths` match |

The always-loaded set has a hard budget, counted in what costs adherence, since instruction-following falls as instructions grow:

| what | ceiling |
|---|---|
| **rules loaded on every `.py`**: top-level bullets with a bold lead | **100** |
| **tokens loaded on every `.py`**, estimated at four characters each | **22,000** |
| rules loaded on a test file: the set above plus `testing.md` | 120 |
| tokens loaded on a test file | 28,000 |
| lines in any one `SKILL.md`, after the front matter | 500 |
| tokens in any one `SKILL.md`, after the front matter | 6,000 |

Claude Code re-attaches about the first 5,000 tokens of a skill after compaction; 6,000 leaves only a short tail to lose.

- **Put what applies to every edit in a rule file with `paths: "**/*.py"`, one topic per file.** A rule with no front matter loads into every session in every language; splitting by topic changes the organisation, not the cost, so split only to give a rule its own address.
- **Keep `new-files.md` the one file with no front matter.** A task that writes into an empty directory reads nothing, so path-scoped rules never load; its few lines buy the rules for that one case.
- **Give every skill `paths`, by default `**/*.py` and `**/pyproject.toml`, plus the other files its work lives in.** Without it every description sits in every session's listing, where a better-matching wrong one displaces the right one; `/name` works whatever `paths` says.
- **Put design in the skills, and write no skill about a library.** A library's API changes with every release; take its traps from its current documentation (context7) and its tests, and write each skill against its own contracts, so it holds whatever library serves it.
- **Keep in the always-loaded set only what is universal and behaviour-changing.** Every Python file could break it, and without it the obvious default is wrong; move to a skill only what a concrete signal in the task points at, like an outbound call, an entry point, an untrusted input or a one-off script.
- **Make every addition displace something, and raise a ceiling only by an argument on record.** Cut what the new rule makes redundant, or a section that belongs in a skill; if nothing can be cut, it becomes a skill. Write a raised ceiling into docs/rules-history.md with the arithmetic, never one adjusted to fit the current size.
- **Keep a skill one `SKILL.md`, and cut what does not fit rather than move it.** A linked file is read in a minority of runs, and a second skill for the same trigger competes in a listing capped at 1% of the context window; trim what the model does unprompted and rules said twice until it fits.
- **Turn a rule no tool checks into a check, or delete it, once it is broken in bulk.** Nothing fails when an unchecked rule is skipped; a rule that belongs on the Definition of Done in `core.md`, which `python-review` walks, goes on both.

## One Rule, One Home

- **Write a rule in exactly one file, and never restate a rule file in a skill.** Copies drift into different policies; cite the rule file in a clause, like "(`errors.md`)", and where they contradict, the rule file wins and the skill is fixed. Between two skills a rule has one owner, and a case where it differs is folded into its own rule.
- **Name a neighbouring skill only in a skill's introduction, once, as a route.** Naming a skill does not load it, so a pointer inside a rule sends the reader to text they do not have; the checker reports a skill named anywhere else.
- **Teach a library's lifetime as the library's own context manager, never a house wrapper or prefix.** A wrapper shown once gets copied around libraries that already have one; a hand-written context manager is for a library with none, named for what it yields.

## Descriptions

- **Write a description as what the skill does, then `ALWAYS invoke this skill when` and the signals, then `Do not ... directly`.** The model sees only the description until it loads a skill, and skips a skill it judges optional; the directive form activates it, where "Use when" leaves the choice to the model. The checker caps it at 400 characters.
- **Make the signals words a task contains, never the rules the skill holds.** No task names a rule.
- **Tell neighbouring descriptions apart in their own words, and close a near miss with `Not for ... (python-x).`** The listing is read as a whole, and a description that matches better than the right one wins.

## Evaluation

- **Keep a rule only for something the model would not do unprompted.** General practice the model already follows costs tokens in every session and dilutes the rules beside it; what earns a place is a measured fact, a library's trap, a decision this project made, or the correction of a wrong default.
- **Test a rule with a realistic task that never mentions it, without the rule first and then with it, a few runs each.** A rule whose task passes without it restates the default and is deleted; seed the task with a file to read, and ask nothing that outranks the rule. The cases live in `evals/python/`, and `evals/run.py --arm both` runs both arms.
- **Move, merge or cut a rule only after its case passes without it there, run before and after against the starting commit.** The model follows what is in its context; a rule that loses keeps its line in the body it left.
