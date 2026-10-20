# claude-rules

Design rules for Python that linters and type checkers cannot see: names, abstractions,
responsibility, encapsulation, module boundaries. For Claude Code.

| Path | What it is |
|---|---|
| `.claude/rules/python.md` | The ruleset. No `paths:`, so Claude Code loads it at the start of every session |
| `.claude/skills/python-review/` | `/python-review`: a review of the current change in its own context |
| `bench/` | The benchmark every change to the ruleset has to pass |
| `docs/benchmark.md` | What was measured and what it showed |

## Install

    ln -s "$PWD/.claude/rules/python.md" ~/.claude/rules/python.md
    ln -s "$PWD/.claude/skills/python-review" ~/.claude/skills/python-review

## Why one always-loaded file

Measured on this benchmark: skills holding rules were never invoked, and a rule with `paths:` never
loaded when the agent worked through grep and sed. The same entries in one file loaded at session
start passed every design check. This is also how ponytail delivers its ruleset.

## Changing the ruleset

A change goes in only when it beats the current file in a paired run. Write the changed ruleset to
`bench/candidate.md`, then:

    bench/run.py --selftest
    bench/run.py --arms rules,candidate --runs 1

Name the task the change should improve and one it could break. A change that moves no number is
not merged, however good the idea.

Write every rule in general words, with no examples, identifiers or lists of cases: the agent
applies a listed rule only to what is listed. Never add a sentence for one failed task; change
the principle the task exposed, and rerun every task.
