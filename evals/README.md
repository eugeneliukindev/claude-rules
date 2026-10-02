# Evals

Does a rule change what the model writes? Each scenario is a realistic task that never mentions
the rule, and a check on the code produced. The runner executes every scenario through
`claude -p` against one or more versions of the rules and prints the pass rate side by side.

```bash
python run.py --self-test                       # checks against fixtures/good and fixtures/bad
python run.py --variant A=.. --variant none=none --repeat 3 --dry-run
python run.py --variant A=.. --variant B=../../claude-rules-variant-b --variant none=none \
    --repeat 3 --jobs 6                         # real sessions: costs money
```

`--variant LABEL=PATH` takes a checkout containing `.claude/rules/python` and
`.claude/skills/python-*`; `LABEL=none` runs without any Python rules. Each session runs in a
temporary `CLAUDE_CONFIG_DIR` holding a symlink to your credentials and exactly that variant's
rules, so `~/.claude` is neither used nor touched. Results — transcript, produced files, verdict —
land in `results/<timestamp>/`, which git ignores. The table also counts runs that opened a
`python-*` skill.

## Adding a scenario

`scenarios/<id>/` holds `prompt.md`, `checks.py` exposing `check(workdir) -> list[Failure]`
(helpers in `evalkit.py`), `seed/` copied into the workdir, and `fixtures/good*/` and
`fixtures/bad*/` for `--self-test`.

**Seed the file the task writes**, even as a one-line stub. Path-scoped rules load only when
Claude *reads* a matching file; a task that writes `x.py` into an empty directory never sees
`core.md`, and the scenario measures nothing.

**Keep the prompt free of instructions that override the rule.** "Make sure it is well
documented" is an explicit request, and it outranks the comment rules by design.

## Reading the result

- Fails without rules, passes with them — the rule works.
- Passes without rules — the rule restates the model's default; a deletion candidate.
- Fails with rules — the rule does not reach the model, or a check is wrong: read the produced
  code before believing either.

Three runs per cell separate a working rule from noise only when the difference is large.
