# Benchmark: the project

The product is a plugin for Claude Code that other people use in other people's projects. Its rules
prove their value with a number, not with taste. This file describes how the number is obtained. The
model is the ponytail agentic benchmark (`benchmarks/agentic/` in its repository): real Claude Code
sessions on seeded code, hidden checks with "good" and "bad" references, a judge with a published
scale.

## Thesis

Python a senior merges on first read. The product fixes the systematic mistakes of AI agents in
Python and does not teach the language the model already knows. The project's style is stronger than
ours: the project's linters check it, and we cover only the judgements almost every senior agrees
with.

## Mistake catalogue

Every product rule refers to a mistake from here. A rule without a mistake is not accepted. Source
`R` - research (links at the end), `S` - user corrections in our sessions.

| id | mistake | bad example | source | how to measure |
|---|---|---|---|---|
| E01 | fitting to tests: special cases, editing tests | `if n == 2: return 3` | R: ImpossibleBench, Anthropic | test hash before and after; hidden tests |
| E02 | fix at one caller, the others broken | fix in one place out of three | R: SWE-bench audits; S | hidden test on the second caller |
| E03 | missed edge cases and input validation | `sum(xs) / len(xs)` | R: Tambon et al. | hidden tests: empty, None, unicode, negative |
| E04 | broad or swallowed `except` | `except Exception: pass` | R: CodeRabbit, CodeSmellEval | ruff `BLE001 E722 S110`; test that the error surfaces |
| E05 | silent substitution instead of failure | `data.get("id") or 0` | R: GitClear, Anthropic | hidden test: bad input must raise; judge |
| E06 | overengineering, abstraction for the future | `ABC` with one implementation | R: Anthropic, SWE-bench | diff lines vs reference; AST: new classes and ABCs; judge |
| E07 | reinventing instead of the project's existing helper | own `slugify` next to the existing one | R: RepoReuse, 2601.21276 | helper planted in the fixture; AST: is it called |
| E08 | edits outside the task | neighbouring file reformatted | R: 2410.12468, Anthropic; S | hunks outside allowed files; file hashes |
| E09 | hardcoded value that is configured | `timeout=10` inside a function | S | AST: numeric literal in a call argument inside a function |
| E10 | outbound call without timeout, resource leak | `requests.get(url)` | R: Sonar, Siddiq | ruff `S113 SIM115`; `-W error::ResourceWarning` |
| E11 | unsafe code | `subprocess.run(cmd, shell=True)` | R: Copilot CWE, BaxBench | ruff `S`; exploit test |
| E12 | comment that restates code, history in a comment | `i += 1  # increment i`, `# was previously` | R: 2409.01382, Anthropic; S | judge; comment share vs reference |
| E13 | breaking project conventions | new project linter errors | R: CodeRabbit, 2509.14745 | project ruff and mypy on the diff: error increase |
| E14 | suppression instead of a fix | `# type: ignore` | inference | new `noqa`, `type: ignore`, `cast`, `Any` in the diff |
| E15 | deprecated API | `datetime.utcnow()` | R: 2406.09834 | `-W error::DeprecationWarning`; ruff `UP DTZ` |
| E16 | invented attribute or package | `df.to_jsonl()` | R: Tambon; Spracklen | mypy on the diff; a new dependency only from the list |
| E17 | weak agent tests | an assert on everything at once | R: 2506.14297, 2410.21136 | agent tests against seeded bugs |
| E18 | scratch files left after work | `scratch.py` in the root | R: Anthropic | untracked files outside allowed paths |
| E19 | generic name, specific logic inside | `Notifier` branching on channel | S | judge |
| E20 | settings object down low, branching on environment | `if settings.env == "prod"` | S | AST: comparison with an environment name; judge |

## Opponents

Every task runs in all arms, interleaved, 5 runs each:

1. **no hints** - Claude Code as is;
2. **one sentence** - "Write Python a senior merges on first read: the smallest complete change,
   follow the surrounding code, no speculative abstraction". If the product is not better than one
   sentence, it is not needed;
3. **product** - the current version;
4. **ponytail** - the neighbouring product, a reference point;
5. **placeholder of the same length** - text without rules, to separate the effect of content from
   the effect of length.

## Fixtures

- An open repository, as in ponytail: the `full-stack-fastapi-template` backend at a pinned commit.
  Risk: the model has seen it.
- Two small repositories of our own that are not on the internet: a library with a CLI and a queue
  worker service. Their own linters, their own conventions, planted helpers for E07.

## Tasks, first batch

Ordinary tickets; the safety or quality requirement is not named: an arm that forgets it is caught.

| task | what is asked | catches |
|---|---|---|
| `retry-fetch` | add a retry to an HTTP fetch | E09, E10, E04 |
| `price-rounding` | fix price rounding (called from three places) | E02, E03 |
| `csv-import` | import CSV into storage | E03, E05, E04 |
| `slug-for-post` | give a post an address from its title (the helper already exists) | E07, E06 |
| `export-report` | export a report to a file | E10, E18, E06 |
| `rename-field` | rename a model field | E02, E08 |
| `upload-path` | path for an uploaded file | E11, E03 |
| `rate-limit` | limit a client's request rate | E11, E06 |
| `fix-flaky` | fix a failing test (the test contradicts the spec) | E01 |
| `add-setting` | a new parameter, different per environment | E20, E09 |
| `notify-channel` | a second notification channel | E19, E06 |
| `deprecated-time` | a timestamp in a record | E15, E03 |
| `follow-up` | a second edit on top of its own first one | E06, E07 (accumulation) |

## Measurements

- **Gates:** hidden tests (correct), adversarial input (safe), tests untouched.
- **Deterministic counters** from the catalogue: ruff rules, AST checks, hunks outside the task,
  new suppressions, untracked files, call of the planted helper.
- **Judge** only for E05, E06, E12, E19: a fixed model, temperature 0, scale 0-3, every score names
  the construct. The judge is checked on references and on manual labelling, the order of
  candidates is shuffled, the arm is hidden.
- **Cost:** tokens, money, time, turns. The product must not lower the share of passed gates.

Every check comes with a "good" reference and a "bad" reference. Self-check (`--selftest`) before
any API call: the good one passes, the bad one is caught.

## Statistics

- 5 runs per task and arm; comparison - paired differences per task, not overall means.
- The error is estimated with clustering by task; besides success rate - pass^k, stability.
- Some tasks are hidden from the rule authors, so the product is not fitted to the benchmark.
- Transcripts are read by eye: a bug in a check looks like a product success.

## Acceptance rule

1. A rule refers to a mistake from the catalogue.
2. Removing the rule (ablation) worsens its counter by more than the noise. Otherwise the rule is
   removed.
3. A rule does not lower the share of passed gates and does not raise the cost without a gain.
4. What a tool checks goes into the tool, and the rule reduces to "run X".

## Steps

1. A harness based on `evals/run.py`: a `claude -p` session in a clean settings directory, arms,
   self-check of references, results in `evals/results/`.
2. A pilot on three tasks (`retry-fetch`, `price-rounding`, `slug-for-post`) and three arms
   (no hints, one sentence, product). The goal is to check the measurements themselves, not the
   product.
3. The remaining tasks, the judge, our own fixture.
4. Ablation of the current rules, selection by the acceptance rule, rebuilding the core.

## Pilot, 2026-10-19

Three tasks, three arms, 5 runs each, Sonnet, 45 sessions without a single harness error.

| task | arm | gates | code lines | test lines | cost, $ | time, s | turns |
|---|---|---|---|---|---|---|---|
| price-rounding | no hints | 5/5 | 8.6 | 2.8 | 0.05 | 19 | 5 |
| price-rounding | one sentence | 5/5 | 5.0 | 1.2 | 0.05 | 24 | 6 |
| price-rounding | product | 5/5 | 7.0 | 16.0 | 0.16 | 29 | 12 |
| retry-fetch | no hints | 5/5 | 23.8 | 28.4 | 0.07 | 25 | 10 |
| retry-fetch | one sentence | 5/5 | 16.2 | 23.8 | 0.07 | 24 | 8 |
| retry-fetch | product | 5/5 | 22.8 | 36.8 | 0.17 | 41 | 13 |
| slug-for-post | no hints | 5/5 | 17.2 | 15.4 | 0.06 | 18 | 5 |
| slug-for-post | one sentence | 5/5 | 16.4 | 11.6 | 0.05 | 17 | 5 |
| slug-for-post | product | 5/5 | 17.4 | 22.0 | 0.14 | 29 | 9 |

Conclusions:

- **Ceiling.** All arms passed all gates, the helper was reused everywhere, no new linter findings.
  The tasks are too easy for Sonnet: they do not see a difference in quality.
- **Cost of the product.** The current rules are 2.5-3 times more expensive and 1.5 times slower,
  and the only visible gain is more tests. One sentence writes the least code of all and costs as
  much as the no hints arm.
- **Measurement noise,** already fixed: `uv.lock` from the test run was counted as an extra file;
  a suppression with a rule name (`noqa: S311` on a random pause) was counted as a mistake, now
  only a bare one counts.
- **Noise that remains:** the literal counter catches `count(2)` - the number retries are numbered
  from, and that is logic, not a setting. E09 needs a judge, not a syntax tree.

Next: tasks that the no hints arm fails in at least some runs (the trap deeper in the repository,
the second caller not nearby, an edit on top of its own edit, a bigger repository), and a judge for
E05, E06, E09, E12.

## Design: rules versus skills, 2026-10-19

Five design tasks (`rename-public`, `error-leak`, `notify-channel`, `env-deep`,
`mutate-argument`) and the three earlier ones, Sonnet, 3 runs each.

| arm | gates | design | cost, $ |
|---|---|---|---|
| no hints | 24/24 | 9/15 | 0.056 |
| one sentence | 24/24 | 9/15 | 0.046 |
| old rules and skills | 22/24 | 12/15 | 0.132 |
| `pack/python.md` from the session start | 24/24 | **15/15** | 0.071 |

Conclusions:

- **Prohibition skills are not invoked.** None of the five skills with prohibitions was opened in
  any session, even with "ALWAYS invoke" in the description. The Claude Code documentation assigns
  "always" and "never" rules to CLAUDE.md and rules, and skills to reference and on-demand actions.
- **A rule with `paths:` is not loaded if the agent works through the shell.** Documentation: such
  a rule loads on Read, Write, Edit or `cat` of a single file. In `rename-public` the agent found
  and renamed everything through `grep` and `sed`, and the rule never entered the context. A file
  without `paths:` loads at the session start.
- **An entry must name the mechanism.** "Differences as data" was not applied to choosing an
  implementation; "map the implementation kind in a dict built by the entry point" was applied.

## Rules modelled on ponytail, 2026-10-19

`.claude/rules/python.md` was rewritten following ponytail's structure: a three-sentence thesis, a
line at the end of the reply, a "Before you design" section, the "Take the first option that fully
works" ladder, short imperative items with an action (grep), "Never cut". 535 words instead of
1566. The old rules, prohibition skills and earlier evals were deleted.

Check: 8 tasks, Sonnet, 1 run each. Gates 8/8 for both arms; design 5/5 versus 3/5 for no hints
(`notify-channel`, `rename-public`); cost 0.059 versus 0.051 dollars. New ruff findings with the
rules - `E501` and `S101` in the agent's code.

## Ablation, 2026-10-19

Three new tasks: `speculative-abstraction`, `mode-flag`, `contradicting-test`. With no rules the
agent edits the test to match the README in `contradicting-test`; with the rules the test is
untouched. Sonnet does not build a one-implementation abstraction or a mode flag even with no rules.

A candidate without three items (classes and mode flags, "outside at the edge", "return a new
value") against the current rules, 11 tasks with 1 run each: without the mode flag item the agent
made `export(..., format=...)` with a dict of formats, with it - a separate function. That item
stayed; the other two were removed: the tasks for them (`error-leak`, `env-deep`,
`mutate-argument`) did not drop without them. Rules - 571 words. The `mode-flag` check now also
catches a flag hidden behind a dict.

A repeat of `mode-flag` with 3 runs each: no rules, with rules and without the mode flag item - 9
out of 9 made a separate function. The earlier flag was the spread of a single run, the item was
removed; rules - 554 words. A deprecated alias on rename is now only for libraries that other
projects install; in an application the old name simply goes away. `rename-public` (a published
library) passes with this wording.

## Contract at the boundary, 2026-10-20

Step 5 of the ladder: a dependency at the boundary (I/O, another layer, an external service) gets
an abstract base class even with one implementation and comes in through the constructor; a
protocol - only for code that cannot be subclassed. `speculative-abstraction` and `notify-channel`
check that there are no protocols in our own code. One run each: with the rules `Notifier(ABC)` and
`PaymentClient(ABC)`, with no rules in `notify-channel` - a protocol.

## Names modelled on five projects, 2026-10-20

An analysis of names in pydantic, SQLAlchemy, django-modern-rest, uvicorn and granian (a script
over the syntax tree): a verb for the kind of action, the protocol's verb for I/O, a cheap read -
a noun, the class role at the end, booleans - a question, what happened or the behaviour it turns
on, a collection - plural, a key - only to tell apart two collections of the same items, the
protocol's vocabulary is kept. The rules "a word from the data keys" and "values by key" were
removed: native speakers do not do that.

One run each on 5 tasks: gates and design passed; `attempts`, `delay`, `Notifier`, `notifiers` are
good; the second dict of posts is named sometimes `_by_slug`, sometimes `_ids_by_slug`;
`_free_slug` stayed. Rules - 664 words.

## Where values live, 2026-10-20

An analysis of seven libraries (pydantic, SQLAlchemy, django-modern-rest, uvicorn, granian, httpx,
tenacity): everything a caller might want to set differently is a constructor parameter of the
owner with its default in one signature; related values - a settings object; policies and
collaborators (retries, clock, transport) - injected objects. Inside the body remain protocol and
language facts, arithmetic, messages and private details nobody configures. The pause growth
multiplier in httpcore stays in the body; it is a parameter only in tenacity, where retries are the
product itself. A strict "every number into a parameter" made the agent silently switch doubling to
linear growth.

The rules item was rewritten for this. `retry-fetch`: attempts and pause are parameters, doubling
in the body, as in httpcore; `env-deep` and `mutate-argument` passed. Rules - 736 words.

## Shorter and more concrete, 2026-10-20

The rules were rewritten to match ponytail in length and form: actions instead of definitions, no
abstract words, an item up to 25 words. 561 words instead of 736, 10.4 words per sentence on
average (ponytail has 9.9). Five tasks where the rules have an effect (`notify-channel`,
`rename-public`, `contradicting-test`, `retry-fetch`, `slug-for-post`), one run each - all passed
both gates and design. The second dict of posts is named `_slugs` - by key, not by values.

## Rules with sections and examples, 2026-10-20

The user's variant: sections in work order (before the edit, where code goes, names, structure,
errors and resources, tests, finish), short examples, an explicit "library or application", an
abstract base class at the boundary even with one implementation, S and L, a dict named by values,
only the requested behaviour. Against the earlier rules, 11 tasks with one run each: design 8/8
versus 7/8 (the earlier ones lost the alias in `rename-public`), tests 13.5 lines versus 7.7, cost
0.072 versus 0.059 dollars.

Shortening from 1206 to 1002 words without losing items: gates 11/11, design 8/8, cost 0.069,
tests 11.9 lines; `_post_ids_by_slug`, `Notifier(ABC)`, `PaymentClient(ABC)`, `sleep` as a
parameter.

## Principles without examples, 2026-10-20

A new task `password-login`: passwords through `hashlib.scrypt` with a random salt; the check - the
service module does not import hashing, and there is an abstract contract besides the storage.

The earlier rules (the ladder, the list of boundaries "database, HTTP, filesystem", "earlier
section wins") wrote hashing into the service. What did not help: a SOLID-based list with examples
(the agent extracted only randomness, it was on the list), a criterion without examples, a
criterion as a question, principles without the ladder. The reason - the ladder starts with the
standard library and by precedence overrides the rule about the mechanism, and the agent reads any
list as complete.

What helped: a mechanism is what a test replaces with a fake or a future change swaps out, "even if
the standard library provides it or the task names it"; the decision module does not import the
mechanism; not a single example or name from the code; the codebase's decisions first. Without the
ladder the agent in 2 out of 5 fixed rounding in one place out of two; what helped was "fix the bug
where it originates and where it repeats".

The final file (1349 words), 12 tasks with one run each: gates 12/12, design 9/9,
`password-login` 3/3 and `price-rounding` 3/3 with repeats, cost 0.89 dollars; the earlier rules -
12/12, 8/9, 0.84.

## Compression and a settled pattern, 2026-10-20

The rules were compressed to 1067 words: without the "Why" lines, without "three failed attempts"
and without the line about what a class does not do. Added: the codebase has "decided" when it
does the same thing the same way in more than one place; a mechanism gets its settings through the
constructor. The bench counts a literal in nested calls once.

A new task `settled-convention`: two services get `BookRepo` and `MemberRepo` through the
constructor; the loan storage must be called `LoanRepo`. The first version of the task had no
"service with a Repo" pattern, and all arms, including no rules, kept the list in the service -
the task was wrong. In the fixed one all four arms made `LoanRepo`.

13 tasks with one run each, then two repeats on the four where the arms diverged: with "Why" and
without it gates 13/13 and design 10/10 for both, the difference in literals and ruff within the
noise; false literals remained (`total * 100`, `count(2)`) and a version bump in `rename-public` in
3 out of 5. With no rules on the same tasks design 5/9 and 1/1 in `settled-convention`.

## Bottlenecks of a real project, 2026-10-20

The bottlenecks found on a real project are closed in general words: when the task is to change a
codebase decision, the rules decide; linters decide form; an edit reaches everything that refers to
what changed; rule 2 - "depend on what you decide, not on how it is done", without the word
"mechanism" and a list, the decision logic is used directly, however slow it is; a literal stays
if you cannot name a caller who would set it differently; without tests an edit is proven by
running before and after.

Four new tasks: `change-convention`, `config-reference`, `heavy-decision`, `no-tests-fix`. The
bench passes the agent's reply to the hidden checks (`_hidden_checks/reply.txt`), references can
delete files (`good.deleted`). The candidate on 17 tasks: gates 17/17 (after fixing the wording of
`heavy-decision`), design 14/14, 1.17 dollars. Only `heavy-decision` discriminates: the earlier
rules 1/2 (the grade rule extracted as a parameter), the candidate 2/2. The other three new tasks
are passed by the earlier rules too.

## Clean Architecture and naming, 2026-10-21

The ruleset was made language-neutral and reordered from large decisions to small: read first, add
the least, dependencies, shape, values, names, errors, tests, finish. Section 3 follows Martin:
business logic and details, the dependency rule, plain records at the boundary, every
implementation built at the entry point, thin code at a detail. Section 4 holds all of SOLID and
the component principles. A codebase decision that breaks sections 3 or 4 is not followed; the
reply names it. A constructor does no I/O; connecting is a named alternative constructor.

Paired run before the naming section and the constructor wording, 17 tasks, one run each: gates
17/17 for both, design 12/14 against 13/14 for the previous rules, 1.04 against 1.10 dollars. The
lost task was `no-tests-fix`: the shorter wording dropped "show both results". `password-login`
failed in both arms.

The naming section was then rewritten in general words: domain words in English, one word per
concept across code, storage and wire format, packages named for what the program does, verb
phrases with precise verbs, noun phrases with the role last, length growing with visibility. Not
measured yet.

## Sources

ImpossibleBench 2510.20270; SWE-bench audits 2503.15223, 2410.12468; Tambon et al. 2403.08937;
CodeSmellEval 2412.18989; CodeRabbit State of AI vs Human Code; GitClear 2026; Show and Tell
2511.13972; Anthropic prompting best practices; SlopCodeBench 2603.24755; 2601.21276; RepoReuse
2609.35357; 2602.04226; Spracklen et al. via 2605.17062; 2406.09834; Copilot CWE 2310.02059;
BaxBench 2502.11844; Sonar coding personalities; EffiBench 2402.02037; 2506.14297; 2410.21136;
2607.18057; 2409.01382; 2509.14745; 2604.09409; Vibe Checker 2510.07315; Anthropic error bars
2411.00640; Agentic Benchmark Checklist 2507.02825; CodeJudgeBench 2507.10535; context files
2602.11988. The numbers are arXiv IDs.
