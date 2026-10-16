#!/usr/bin/env python3
"""Run the behaviour evals in evals/python/ against `claude -p`, with the rules and without.

Each case is a realistic task that never names the rule it tests. It runs in a fresh working
directory seeded with the case's files, under a fresh CLAUDE_CONFIG_DIR: the `with` arm copies
`.claude/rules/python/` and `.claude/skills/python-*` into it, the `without` arm leaves it empty, so
neither arm sees the user's own rules, skills, hooks or plugins. Afterwards the case's checks run:

- `skills` and `not_skills`: skills the session invoked, or must not have (the `with` arm only);
- `reads`: reference files the session read, by path suffix (the `with` arm only);
- `code`: a regex that must (`match`) or must not (`no_match`) occur in the files matching a glob.

A case passes when every check passes; a check that passes in the `without` arm too tests what the
model already does, and its rule is a candidate for deletion (`evaluation.md`). Results are written
to evals/results/, which git ignores.

    evals/run.py --check                       # validate the case files only, no runs
    evals/run.py --arm both --model sonnet     # every case, both arms
    evals/run.py --only python-sync --runs 3   # one file, three runs per arm

The child sessions authenticate with ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN when either is
set, and otherwise with the access token of the current login, read from `.credentials.json` and
passed in the environment, so the empty config directory holds no credential and never refreshes
one.

Exit codes: 0 every `with` run passed, 1 a failure, 2 a case file is malformed or no login.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

_REPOSITORY: Final = Path(__file__).resolve().parent.parent
_CASES_DIRECTORY: Final = _REPOSITORY / "evals" / "python"
_RESULTS_DIRECTORY: Final = _REPOSITORY / "evals" / "results"
_RULES_DIRECTORY: Final = _REPOSITORY / ".claude" / "rules" / "python"
_SKILLS_DIRECTORY: Final = _REPOSITORY / ".claude" / "skills"
_CASE_KEYS: Final = frozenset({"id", "prompt", "files", "skills", "not_skills", "reads", "code"})
_CODE_KEYS: Final = frozenset({"files", "match", "no_match", "why"})
_RUN_TIMEOUT_SECONDS: Final = 900
_TOKEN_MARGIN_SECONDS: Final = 1800
_AUTH_VARIABLES: Final = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
_EXIT_CLEAN: Final = 0
_EXIT_FAILED: Final = 1
_EXIT_MALFORMED: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class _Check:
    description: str
    passed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class _Session:
    skills: frozenset[str]
    reads: tuple[str, ...]
    error: str | None = None
    cost_usd: float = 0.0
    output_tokens: int = 0
    duration_ms: int = 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate the case files and exit")
    parser.add_argument("--arm", choices=("with", "without", "both"), default="with")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--only", help="the case file to run, without .json")
    parser.add_argument("--case", help="the one case id to run")
    parser.add_argument("--runs", type=int, default=1)
    arguments = parser.parse_args()

    case_files = sorted(_CASES_DIRECTORY.glob(f"{arguments.only or '*'}.json"))
    problems = [problem for path in case_files for problem in _case_file_problems(path)]
    if problems or not case_files:
        print("\n".join(problems) or "no case files", file=sys.stderr)
        sys.exit(_EXIT_MALFORMED)
    if arguments.check:
        print(f"{len(case_files)} case files, {sum(len(_cases(p)) for p in case_files)} cases: ok")
        sys.exit(_EXIT_CLEAN)

    auth = _auth_environment()
    if auth is None:
        print("no login: run claude once, or set CLAUDE_CODE_OAUTH_TOKEN", file=sys.stderr)
        sys.exit(_EXIT_MALFORMED)
    arms = ("with", "without") if arguments.arm == "both" else (arguments.arm,)
    results = [
        _run_case(case, arm=arm, model=arguments.model, run=run, auth=auth)
        for path in case_files
        for case in _cases(path)
        if arguments.case in (None, case["id"])
        for arm in arms
        for run in range(1, arguments.runs + 1)
    ]
    _RESULTS_DIRECTORY.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (_RESULTS_DIRECTORY / f"{stamp}-{arguments.model}.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _print_summary(results)
    with_failed = any(not r["passed"] for r in results if r["arm"] == "with")
    sys.exit(_EXIT_FAILED if with_failed else _EXIT_CLEAN)


def _auth_environment() -> dict[str, str] | None:
    if any(os.environ.get(name) for name in _AUTH_VARIABLES):
        return {}
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    try:
        login = json.loads((config / ".credentials.json").read_text(encoding="utf-8"))
        token = login["claudeAiOauth"]
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    expires_at = datetime.fromtimestamp(token["expiresAt"] / 1000, UTC)
    if (expires_at - datetime.now(UTC)).total_seconds() < _TOKEN_MARGIN_SECONDS:
        return None
    return {"CLAUDE_CODE_OAUTH_TOKEN": str(token["accessToken"])}


def _cases(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))["cases"]
    return cases


def _case_file_problems(path: Path) -> Iterator[str]:
    try:
        cases = _cases(path)
    except (KeyError, json.JSONDecodeError) as error:
        yield f"{path.name}: {error}"
        return
    skill_names = {
        d.name for d in _SKILLS_DIRECTORY.glob("python-*/") if (d / "SKILL.md").is_file()
    }
    for case in cases:
        where = f"{path.name}:{case.get('id')}"
        if unknown := set(case) - _CASE_KEYS:
            yield f"{where}: unknown keys {sorted(unknown)}"
        if not case.get("id") or not case.get("prompt"):
            yield f"{where}: id and prompt are required"
        for skill in [*_strings(case.get("skills")), *_strings(case.get("not_skills"))]:
            if skill not in skill_names:
                yield f"{where}: no skill {skill}"
        for read in _strings(case.get("reads")):
            in_skill = any(_SKILLS_DIRECTORY.glob(f"python-*/{read}"))
            if not in_skill and not (_SKILLS_DIRECTORY / read).is_file():
                yield f"{where}: no reference file {read}"
        for check in _mappings(case.get("code")):
            if unknown := set(check) - _CODE_KEYS:
                yield f"{where}: unknown code keys {sorted(unknown)}"
            patterns = [p for p in (check.get("match"), check.get("no_match")) if p is not None]
            if len(patterns) != 1 or not check.get("files"):
                yield f"{where}: a code check has files and exactly one of match, no_match"
            for pattern in patterns:
                try:
                    re.compile(str(pattern))
                except re.error as error:
                    yield f"{where}: {pattern!r}: {error}"


def _run_case(
    case: Mapping[str, object], *, arm: str, model: str, run: int, auth: Mapping[str, str]
) -> dict[str, object]:
    with (
        tempfile.TemporaryDirectory(prefix="eval-work-") as work,
        tempfile.TemporaryDirectory(prefix="eval-config-") as config,
    ):
        working_directory, config_directory = Path(work), Path(config)
        for relative_path, content in _string_mapping(case.get("files")).items():
            target = working_directory / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        if arm == "with":
            shutil.copytree(_RULES_DIRECTORY, config_directory / "rules" / "python")
            for skill in _SKILLS_DIRECTORY.glob("python-*/"):
                shutil.copytree(skill, config_directory / "skills" / skill.name)
        completed = subprocess.run(
            [
                "claude",
                "-p",
                str(case["prompt"]),
                "--model",
                model,
                "--output-format",
                "stream-json",
                "--verbose",
                "--permission-mode",
                "bypassPermissions",
            ],
            cwd=working_directory,
            env={**os.environ, **auth, "CLAUDE_CONFIG_DIR": str(config_directory)},
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT_SECONDS,
            check=False,
        )
        session = _session(completed.stdout.splitlines())
        seeded_lines = sum(
            content.count("\n")
            for name, content in _string_mapping(case.get("files")).items()
            if name.endswith(".py")
        )
        written_lines = sum(
            path.read_text(encoding="utf-8", errors="replace").count("\n")
            for path in working_directory.rglob("*.py")
        )
        checks = list(_checks(case, session=session, working_directory=working_directory, arm=arm))
    passed = completed.returncode == 0 and all(check.passed for check in checks)
    print(f"{'PASS' if passed else 'FAIL'} {arm:7} {case['id']} (run {run})", flush=True)
    if session.error:
        print(f"     - the session failed: {session.error}", flush=True)
    for check in checks:
        if not check.passed:
            print(f"     - {check.description}", flush=True)
    return {
        "case": case["id"],
        "arm": arm,
        "model": model,
        "run": run,
        "passed": passed,
        "exit_code": completed.returncode,
        "error": session.error,
        "skills": sorted(session.skills),
        "reads": list(session.reads),
        "checks": [{"check": c.description, "passed": c.passed} for c in checks],
        "cost_usd": session.cost_usd,
        "output_tokens": session.output_tokens,
        "duration_ms": session.duration_ms,
        "added_lines": written_lines - seeded_lines,
    }


def _session(lines: Sequence[str]) -> _Session:
    skills: set[str] = set()
    reads: list[str] = []
    error: str | None = None
    cost_usd = 0.0
    output_tokens = 0
    duration_ms = 0
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            if event.get("is_error"):
                error = str(event.get("result"))
            cost_usd = float(event.get("total_cost_usd") or 0)
            output_tokens = int((event.get("usage") or {}).get("output_tokens") or 0)
            duration_ms = int(event.get("duration_ms") or 0)
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            tool_input = block.get("input", {})
            if block.get("name") == "Skill":
                skills.add(str(tool_input.get("skill", "")).split(":")[-1])
            elif block.get("name") == "Read":
                reads.append(str(tool_input.get("file_path", "")))
    return _Session(
        skills=frozenset(skills),
        reads=tuple(reads),
        error=error,
        cost_usd=cost_usd,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )


def _checks(
    case: Mapping[str, object], *, session: _Session, working_directory: Path, arm: str
) -> Iterator[_Check]:
    if arm == "with":
        for skill in _strings(case.get("skills")):
            yield _Check(description=f"invokes {skill}", passed=skill in session.skills)
        for skill in _strings(case.get("not_skills")):
            yield _Check(description=f"leaves {skill}", passed=skill not in session.skills)
        for read in _strings(case.get("reads")):
            passed = any(path.endswith(read) for path in session.reads)
            yield _Check(description=f"reads {read}", passed=passed)
    for check in _mappings(case.get("code")):
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in sorted(working_directory.glob(str(check["files"])))
            if path.is_file()
        )
        if "match" in check:
            passed = re.search(str(check["match"]), text, re.MULTILINE) is not None
            verb = "has"
        else:
            passed = re.search(str(check["no_match"]), text, re.MULTILINE) is None
            verb = "lacks"
        pattern = check.get("match", check.get("no_match"))
        description = f"{check['files']} {verb} /{pattern}/"
        if "why" in check:
            description += f" — {check['why']}"
        yield _Check(description=description, passed=passed)


def _print_summary(results: Sequence[Mapping[str, object]]) -> None:
    for arm in ("with", "without"):
        arm_results = [r for r in results if r["arm"] == arm]
        if not arm_results:
            continue
        checks = [c for r in arm_results for c in _mappings(r["checks"])]
        passed_checks = sum(1 for c in checks if c["passed"])
        passed_cases = sum(1 for r in arm_results if r["passed"])
        print(
            f"{arm}: {passed_cases}/{len(arm_results)} cases, {passed_checks}/{len(checks)} checks"
        )
        runs = len(arm_results)
        print(
            f"{arm}: per run {sum(_number(r['cost_usd']) for r in arm_results) / runs:.4f} USD,"
            f" {sum(_number(r['output_tokens']) for r in arm_results) / runs:.0f} output tokens,"
            f" {sum(_number(r['duration_ms']) for r in arm_results) / runs / 1000:.1f} s,"
            f" {sum(_number(r['added_lines']) for r in arm_results) / runs:.0f} added lines"
        )


def _number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _strings(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _mappings(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_mapping(value: object) -> dict[str, str]:
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


if __name__ == "__main__":
    main()
