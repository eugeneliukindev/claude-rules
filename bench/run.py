#!/usr/bin/env python3
"""Run the agentic benchmark: Claude Code sessions on seeded repositories, scored on what they leave.

Each task in bench/tasks/ holds a `seed/` repository, a `prompt` in `task.json`, hidden checks in
`hidden/` and two reference overlays: `good/` must pass every gate and raise no flag, `bad/` must
raise every flag in `expect_bad`. `--selftest` proves both before any session is paid for.

An arm decides what the session's empty CLAUDE_CONFIG_DIR holds:

- `baseline`: nothing;
- `oneliner`: a CLAUDE.md with one sentence of advice;
- `rules`: this repository's `AGENTS.md` as the always-loaded `rules/design.md`, and its skills;
- `candidate`: the same skills with `bench/candidate.md` as the ruleset, a change measured before it lands.

Measured per session, after the agent stops and before the hidden checks are copied in:

- `gates`: every hidden `test_gate_*` passes; `design`: every hidden `test_design_*` passes, a check
  of a design entry rather than of behaviour; `extras` counts the other hidden tests that pass;
- `visible_ok`: the seed's own tests still pass, and `tests_modified` counts lines of them removed or rewritten;
- `src_added`, `tests_added`: added lines of source and of tests, from `git diff`;
- `out_of_scope`: changed or new files outside the task's `allowed` globs, scratch files included;
- `suppressions`: bare `noqa` and `type: ignore`, naming no rule, on added lines;
- `ruff_new`: lint findings under the seed's own config, minus the seed's;
- `literal_args`: numeric literals other than 0 and 1 in call arguments inside functions, minus the seed's;
- `new_classes`: classes added to source;
- `reuse`: for a task that plants a helper, the file calls it and repeats none of its internals.

    bench/run.py --selftest
    bench/run.py --tasks retry-fetch --arms baseline,product --runs 1
    bench/run.py --runs 5 --jobs 3
"""

import argparse
import ast
import fnmatch
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

_REPOSITORY: Final = Path(__file__).resolve().parent.parent
_TASKS: Final = _REPOSITORY / "bench" / "tasks"
_RESULTS: Final = _REPOSITORY / "bench" / "results"
_PYTHON: Final = _REPOSITORY / "bench" / ".venv" / "bin" / "python"
_RUFF: Final = _REPOSITORY / "bench" / ".venv" / "bin" / "ruff"
_RULESET: Final = _REPOSITORY / "AGENTS.md"
_SKILLS: Final = _REPOSITORY / "skills"
_HIDDEN_DIRECTORY: Final = "_hidden_checks"
_ONELINER: Final = (
    "Write Python a senior engineer merges on the first read: the smallest complete change, "
    "follow the surrounding code, no speculative abstraction.\n"
)
_ARMS: Final = ("baseline", "oneliner", "rules", "candidate")
# a ruleset under test, measured against the current one before it replaces it
_CANDIDATE: Final = _REPOSITORY / "bench" / "candidate.md"
_SESSION_TIMEOUT: Final = 900
_CHECK_TIMEOUT: Final = 120
_AUTH_VARIABLES: Final = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
_TRIVIAL_NUMBERS: Final = frozenset({0, 1})
# keywords whose number is part of the call's meaning, never a setting
_FIXED_KEYWORDS: Final = frozenset({"stacklevel", "maxsplit"})
# a suppression that names its rule is a decision; a bare one silences whatever comes
_BARE_SUPPRESSION: Final = re.compile(r"#\s*noqa(?!:)|#\s*type:\s*ignore(?!\[)")


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    name: str
    directory: Path
    prompt: str
    allowed: tuple[str, ...]
    expect_bad: tuple[str, ...]
    reuse: Mapping[str, object] | None
    seed_passes: bool


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true", help="check the references and exit")
    parser.add_argument("--tasks", help="comma-separated task names, all by default")
    parser.add_argument("--arms", default=",".join(_ARMS))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--keep", type=Path, help="copy every finished workspace here")
    arguments = parser.parse_args()

    tasks = [task for task in _load_tasks() if not arguments.tasks or task.name in arguments.tasks.split(",")]
    if arguments.selftest:
        sys.exit(0 if all([_selftest(task) for task in tasks]) else 1)
    auth = _auth_environment()
    if auth is None:
        sys.exit("no login: set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN, or log in to Claude Code")
    arms = arguments.arms.split(",")
    jobs = [(task, arm, run) for run in range(1, arguments.runs + 1) for task in tasks for arm in arms]
    random.shuffle(jobs)
    _RESULTS.mkdir(exist_ok=True)
    results_path = _RESULTS / f"{datetime.now(UTC):%Y%m%d-%H%M%S}.jsonl"
    with ThreadPoolExecutor(max_workers=arguments.jobs) as pool, results_path.open("w") as results_file:
        futures = [
            pool.submit(_run_session, task, arm=arm, run=run, model=arguments.model, auth=auth, keep=arguments.keep)
            for task, arm, run in jobs
        ]
        results = []
        for future in futures:
            result = future.result()
            results.append(result)
            results_file.write(json.dumps(result) + "\n")
            results_file.flush()
    _print_summary(results)
    print(f"\nresults: {results_path}")


def _load_tasks() -> list[Task]:
    tasks = []
    for path in sorted(_TASKS.glob("*/task.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        tasks.append(
            Task(
                name=path.parent.name,
                directory=path.parent,
                prompt=spec["prompt"],
                allowed=tuple(spec["allowed"]),
                expect_bad=tuple(spec["expect_bad"]),
                reuse=spec.get("reuse"),
                seed_passes=spec.get("seed_passes", False),
            )
        )
    return tasks


def _selftest(task: Task) -> bool:
    good_overlay = "good" if (task.directory / "good").exists() else None
    seed, good, bad = (_score_reference(task, overlay) for overlay in (None, good_overlay, "bad"))
    good_flags, bad_flags = _flags(good), _flags(bad)
    # the seed must not already pass, or the task measures nothing, unless leaving it is the answer
    passed = seed["gates"] == task.seed_passes and not good_flags and set(task.expect_bad) <= bad_flags
    print(
        f"{'OK  ' if passed else 'FAIL'} {task.name}: seed gates {seed['gates']}, "
        f"good flags {sorted(good_flags)}, bad flags {sorted(bad_flags)}"
    )
    return passed


def _score_reference(task: Task, overlay: str | None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="bench-ref-") as work:
        workspace = Path(work)
        _seed(task, workspace)
        if overlay is not None:
            shutil.copytree(task.directory / overlay, workspace, dirs_exist_ok=True)
        deleted = task.directory / f"{overlay}.deleted"
        for name in deleted.read_text(encoding="utf-8").split() if deleted.exists() else ():
            (workspace / name).unlink()
        reply = task.directory / f"{overlay}.reply.txt"
        return _measure(task, workspace, reply=reply.read_text(encoding="utf-8") if reply.exists() else "")


def _flags(metrics: Mapping[str, object]) -> set[str]:
    flags = set()
    if not metrics["gates"]:
        flags.add("gates")
    for name in ("literal_args", "ruff_new", "out_of_scope", "suppressions", "tests_modified"):
        if int(metrics[name]) > 0:  # type: ignore[call-overload]
            flags.add(name)
    if metrics.get("reuse") is False:
        flags.add("reuse")
    if metrics.get("design") is False:
        flags.add("design")
    return flags


def _seed(task: Task, workspace: Path) -> None:
    shutil.copytree(task.directory / "seed", workspace, dirs_exist_ok=True)
    for command in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "seed"],
    ):
        subprocess.run(command, cwd=workspace, check=True)


def _run_session(
    task: Task, *, arm: str, run: int, model: str, auth: Mapping[str, str], keep: Path | None
) -> dict[str, object]:
    with (
        tempfile.TemporaryDirectory(prefix="bench-work-") as work,
        tempfile.TemporaryDirectory(prefix="bench-config-") as config,
    ):
        workspace, config_directory = Path(work), Path(config)
        _seed(task, workspace)
        _configure(arm, config_directory)
        completed = subprocess.run(
            [
                "claude", "-p", task.prompt, "--model", model, "--output-format", "stream-json", "--verbose",
                "--permission-mode", "bypassPermissions",
            ],
            cwd=workspace,
            env={**os.environ, **auth, "CLAUDE_CONFIG_DIR": str(config_directory)},
            capture_output=True,
            text=True,
            timeout=_SESSION_TIMEOUT,
            check=False,
        )
        metrics = _measure(task, workspace, reply=_reply_of(completed.stdout))
        if keep is not None:
            shutil.copytree(workspace, keep / f"{task.name}-{arm}-{run}", dirs_exist_ok=True)
    session = _session_summary(completed.stdout)
    result = {"task": task.name, "arm": arm, "run": run, "model": model, **session, **metrics}
    print(
        f"{'PASS' if metrics['gates'] else 'FAIL'} {arm:8} {task.name} run {run} "
        f"flags {sorted(_flags(metrics))} skills {session['skills']}",
        flush=True,
    )
    return result


def _configure(arm: str, config_directory: Path) -> None:
    if arm == "oneliner":
        (config_directory / "CLAUDE.md").write_text(_ONELINER, encoding="utf-8")
    elif arm in {"rules", "candidate"}:
        shutil.copytree(_SKILLS, config_directory / "skills")
        (config_directory / "rules").mkdir()
        ruleset = _RULESET if arm == "rules" else _CANDIDATE
        shutil.copy(ruleset, config_directory / "rules" / "design.md")


def _session_summary(stdout: str) -> dict[str, object]:
    summary: dict[str, object] = {
        "error": "no result event", "cost_usd": 0.0, "output_tokens": 0, "duration_ms": 0, "turns": 0,
    }
    skills: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "Skill":
                    skills.append(str(block.get("input", {}).get("skill", "")).split(":")[-1])
        elif event.get("type") == "result":
            summary = {
                "error": str(event.get("result")) if event.get("is_error") else None,
                "cost_usd": float(event.get("total_cost_usd") or 0),
                "output_tokens": int((event.get("usage") or {}).get("output_tokens") or 0),
                "duration_ms": int(event.get("duration_ms") or 0),
                "turns": int(event.get("num_turns") or 0),
            }
    return {**summary, "skills": skills}


def _reply_of(stdout: str) -> str:
    """The agent's final reply, for checks on what it reports."""
    for line in reversed(stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            return str(event.get("result") or "")
    return ""


def _measure(task: Task, workspace: Path, *, reply: str = "") -> dict[str, object]:
    changed = _changed_files(workspace)
    seed = task.directory / "seed"
    sources = [name for name in changed if name.endswith(".py") and not _is_test(name) and (workspace / name).exists()]
    metrics: dict[str, object] = {
        "changed": changed,
        "out_of_scope": sum(not any(fnmatch.fnmatch(name, glob) for glob in task.allowed) for name in changed),
        **_added_lines(workspace),
        "ruff_codes": (ruff_codes := _ruff_new(workspace, seed)),
        "ruff_new": len(ruff_codes),
        "literal_args": sum(max(0, _literal_args(workspace / name) - _literal_args(seed / name)) for name in sources),
        "new_classes": sum(max(0, _classes(workspace / name) - _classes(seed / name)) for name in sources),
        "visible_ok": _pytest(workspace, "tests")[0] if (workspace / "tests").exists() else True,
    }
    if task.reuse is not None:
        metrics["reuse"] = _reuses(workspace, task.reuse)
    shutil.copytree(task.directory / "hidden", workspace / _HIDDEN_DIRECTORY, dirs_exist_ok=True)
    # hidden checks read the reply here: it is not part of the workspace the agent left
    (workspace / _HIDDEN_DIRECTORY / "reply.txt").write_text(reply, encoding="utf-8")
    _, outcomes = _pytest(workspace, _HIDDEN_DIRECTORY)
    gates = {name: passed for name, passed in outcomes.items() if name.startswith("test_gate")}
    design = {name: passed for name, passed in outcomes.items() if name.startswith("test_design")}
    metrics["gates"] = bool(gates) and all(gates.values())
    metrics["gates_passed"] = sum(gates.values())
    metrics["design"] = all(design.values()) if design else None
    metrics["design_passed"] = sum(design.values())
    metrics["extras"] = sum(
        passed for name, passed in outcomes.items() if not name.startswith(("test_gate", "test_design"))
    )
    metrics["hidden"] = outcomes
    return metrics


def _changed_files(workspace: Path) -> list[str]:
    tracked = _git(workspace, "diff", "--name-only", "HEAD").split()
    untracked = _git(workspace, "ls-files", "--others", "--exclude-standard").split()
    return sorted({*tracked, *untracked} - {""})


def _added_lines(workspace: Path) -> dict[str, int]:
    _git(workspace, "add", "-A")
    diff = _git(workspace, "diff", "--cached", "-U0", "HEAD")
    _git(workspace, "reset", "-q")
    counts = {"src_added": 0, "tests_added": 0, "suppressions": 0, "tests_modified": 0}
    current = ""
    for line in diff.splitlines():
        if line.startswith("--- "):
            continue
        if line.startswith("+++ "):
            current = line.removeprefix("+++ b/")
        elif line.startswith("-") and _is_test(current) and line[1:].strip():
            # a removed or rewritten line of a seed test; an added test is not counted
            counts["tests_modified"] += 1
        elif line.startswith("+") and current.endswith(".py"):
            counts["tests_added" if _is_test(current) else "src_added"] += bool(line[1:].strip())
            counts["suppressions"] += bool(_BARE_SUPPRESSION.search(line))
    return counts


def _is_test(name: str) -> bool:
    return name.startswith("tests/") or Path(name).name.startswith("test_")


def _git(workspace: Path, *arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=workspace, capture_output=True, text=True, check=False).stdout


def _ruff_new(workspace: Path, seed: Path) -> list[str]:
    """Rule codes found beyond the seed's, per file, so a removed finding never hides an added one."""
    before, after = _ruff_findings(seed), _ruff_findings(workspace)
    return sorted(code for (name, code), count in after.items() for _ in range(max(0, count - before[name, code])))


def _ruff_findings(directory: Path) -> Counter[tuple[str, str]]:
    completed = subprocess.run(
        [str(_RUFF), "check", "--no-cache", "--exit-zero", "--output-format", "json", "--exclude", _HIDDEN_DIRECTORY, "."],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        findings = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return Counter()
    return Counter((str(Path(item["filename"]).relative_to(directory.resolve())), str(item["code"])) for item in findings)


def _parsed(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _literal_args(path: Path) -> int:
    tree = _parsed(path)
    if tree is None:
        return 0
    # a number inside nested calls is one literal, counted once
    found: set[int] = set()
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for call in ast.walk(function):
            if not isinstance(call, ast.Call):
                continue
            arguments = [*call.args, *(kw.value for kw in call.keywords if kw.arg not in _FIXED_KEYWORDS)]
            for argument in arguments:
                found.update(id(number) for number in _tunable_numbers(argument))
    return len(found)


def _tunable_numbers(node: ast.AST) -> Iterator[ast.Constant]:
    """Numbers in `node` other than 0, 1 and the base of a power of two."""
    powers_of_two = {
        id(item.left) for item in ast.walk(node)
        if isinstance(item, ast.BinOp) and isinstance(item.op, ast.Pow) and isinstance(item.left, ast.Constant)
    }
    for item in ast.walk(node):
        if (
            isinstance(item, ast.Constant)
            and isinstance(item.value, int | float)
            and not isinstance(item.value, bool)
            and item.value not in _TRIVIAL_NUMBERS
            and id(item) not in powers_of_two
        ):
            yield item


def _classes(path: Path) -> int:
    tree = _parsed(path)
    return 0 if tree is None else sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))


def _reuses(workspace: Path, reuse: Mapping[str, object]) -> bool:
    path = workspace / str(reuse["file"])
    tree = _parsed(path)
    if tree is None:
        return False
    calls = {
        node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    text = path.read_text(encoding="utf-8")
    forbidden = reuse.get("forbid") or []
    return str(reuse["calls"]) in calls and not any(str(item) in text for item in forbidden)  # type: ignore[union-attr]


def _pytest(workspace: Path, target: str) -> tuple[bool, dict[str, bool]]:
    report = workspace / ".bench-report.xml"
    completed = subprocess.run(
        [str(_PYTHON), "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={report}", target],
        cwd=workspace,
        env={**os.environ, "PYTHONPATH": str(workspace), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=_CHECK_TIMEOUT,
        check=False,
    )
    outcomes: dict[str, bool] = {}
    if report.exists():
        for case in ElementTree.parse(report).getroot().iter("testcase"):
            outcomes[case.get("name", "")] = not any(child.tag in {"failure", "error", "skipped"} for child in case)
        report.unlink()
    return completed.returncode == 0, outcomes


def _auth_environment() -> dict[str, str] | None:
    if any(os.environ.get(name) for name in _AUTH_VARIABLES):
        return {}
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    try:
        token = json.loads((config / ".credentials.json").read_text(encoding="utf-8"))["claudeAiOauth"]
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    return {"CLAUDE_CODE_OAUTH_TOKEN": str(token["accessToken"])}


def _print_summary(results: Sequence[Mapping[str, object]]) -> None:
    by_cell: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for result in results:
        by_cell[str(result["task"]), str(result["arm"])].append(result)
    columns = ("gates", "design", "extras", "literal_args", "ruff_new", "out_of_scope", "src_added", "new_classes", "reuse", "cost_usd", "output_tokens")
    print("\ntask             arm       runs " + " ".join(f"{column:>12}" for column in columns))
    for (task, arm), cell in sorted(by_cell.items()):
        values = []
        for column in columns:
            numbers = [float(result[column]) for result in cell if result.get(column) is not None]  # type: ignore[arg-type]
            values.append(f"{statistics.mean(numbers):12.2f}" if numbers else f"{'-':>12}")
        print(f"{task:16} {arm:9} {len(cell):4} " + " ".join(values))


if __name__ == "__main__":
    main()
