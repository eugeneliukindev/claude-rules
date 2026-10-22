# claude-rules

Code design rules that linters and type checkers cannot see: names, abstractions,
responsibility, encapsulation, module boundaries. For Claude Code and any agent that reads
`AGENTS.md` and Agent Skills: Codex, Zed, and the rest.

| Path | What it is |
|---|---|
| `AGENTS.md` | The ruleset. No `paths:`, so every agent loads it at the start of every session |
| `skills/python-review/` | `/python-review`: a review of the current change in its own context |
| `install.sh` | Links both into each agent's home config |
| `bench/` | The benchmark every change to the ruleset has to pass |
| `docs/benchmark.md` | What was measured and what it showed |

## Install

    ./install.sh

It links `AGENTS.md` to `~/.claude/rules/design.md`, `~/.codex/AGENTS.md` and
`~/.config/zed/AGENTS.md`, and each skill into `~/.claude/skills/` (Claude Code reads only this)
and `~/.agents/skills/` (the other agents). A target holding a different file is skipped, never
overwritten: merge it into `AGENTS.md` by hand and rerun.

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
