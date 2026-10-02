"""Run eval scenarios through Claude Code against one or more versions of the rules, and compare."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Final

from evalkit import Failure

_EVALS_ROOT: Final = Path(__file__).resolve().parent
_SCENARIOS_ROOT: Final = _EVALS_ROOT / "scenarios"
_RESULTS_ROOT: Final = _EVALS_ROOT / "results"
_CREDENTIALS: Final = Path.home() / ".claude" / ".credentials.json"
_NO_RULES: Final = "none"
_EXIT_OK: Final = 0
_EXIT_FAILED: Final = 1
_EXIT_USAGE: Final = 2

type _Check = Callable[[Path], list[Failure]]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Variant:
    label: str
    rules_root: Path | None


@dataclass(frozen=True, slots=True, kw_only=True)
class _RunResult:
    variant: str
    scenario: str
    attempt: int
    passed: bool
    failures: list[str]
    skills_loaded: list[str]
    cost_usd: float
    error: str


def _load_check(scenario: str) -> _Check:
    spec = spec_from_file_location(f"checks_{scenario}", _SCENARIOS_ROOT / scenario / "checks.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load checks for {scenario}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check  # type: ignore[no-any-return]  # checks.py modules are untyped plugins


def _build_config_dir(variant: _Variant, into: Path) -> None:
    """A Claude config dir holding the credentials and exactly this variant's Python rules."""
    into.mkdir(parents=True)
    (into / ".credentials.json").symlink_to(_CREDENTIALS)
    if variant.rules_root is None:
        return
    source = variant.rules_root / ".claude"
    shutil.copytree(source / "rules" / "python", into / "rules" / "python")
    for skill in sorted((source / "skills").glob("python-*")):
        shutil.copytree(skill, into / "skills" / skill.name)


def _skills_in_transcript(transcript: str) -> tuple[list[str], float]:
    skills: list[str] = []
    cost = 0.0
    for line in transcript.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            cost = float(event.get("total_cost_usd") or 0.0)
        if event.get("type") != "assistant":
            continue
        for item in event.get("message", {}).get("content", []):
            if item.get("type") == "tool_use" and item.get("name") == "Skill":
                skills.append(str(item.get("input", {}).get("skill", "?")))
    return skills, cost


def _run_one(
    variant: _Variant, scenario: str, attempt: int, *, model: str, timeout_seconds: int, out: Path
) -> _RunResult:
    run_dir = out / variant.label / scenario / str(attempt)
    run_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="rules-eval-") as scratch:
        config_dir = Path(scratch) / "config"
        workdir = Path(scratch) / "work"
        _build_config_dir(variant, config_dir)
        seed = _SCENARIOS_ROOT / scenario / "seed"
        if seed.is_dir():
            shutil.copytree(seed, workdir)
        else:
            workdir.mkdir()
        prompt = (_SCENARIOS_ROOT / scenario / "prompt.md").read_text(encoding="utf-8")
        command = [
            "claude", "-p", prompt,
            "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json", "--verbose",
            "--no-session-persistence",
            "--model", model,
        ]
        environment = {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir)}
        error = ""
        try:
            completed = subprocess.run(
                command, cwd=workdir, env=environment, capture_output=True, text=True,
                timeout=timeout_seconds, check=False,
            )
            transcript = completed.stdout
            if completed.returncode != 0:
                error = f"claude exited {completed.returncode}: {completed.stderr.strip()[:300]}"
        except subprocess.TimeoutExpired as timeout:
            transcript = timeout.stdout.decode() if isinstance(timeout.stdout, bytes) else ""
            error = f"timed out after {timeout_seconds}s"
        (run_dir / "transcript.jsonl").write_text(transcript, encoding="utf-8")
        shutil.copytree(workdir, run_dir / "work", ignore=shutil.ignore_patterns("__pycache__"))
        (config_dir / ".credentials.json").unlink()

    failures = [str(failure) for failure in _load_check(scenario)(run_dir / "work")]
    skills, cost = _skills_in_transcript(transcript)
    result = _RunResult(
        variant=variant.label, scenario=scenario, attempt=attempt,
        passed=not failures and not error, failures=failures, skills_loaded=skills,
        cost_usd=cost, error=error,
    )
    (run_dir / "result.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    print(
        f"{variant.label:>10} {scenario:<22} #{attempt} {'pass' if result.passed else 'FAIL'}"
        f" skills={','.join(skills) or '-'} ${cost:.2f}",
        file=sys.stderr,
    )
    return result


def _print_table(results: Sequence[_RunResult], variants: Sequence[_Variant]) -> None:
    scenarios = sorted({result.scenario for result in results})
    header = f"{'scenario':<22}" + "".join(f"{variant.label:>22}" for variant in variants)
    print(header)
    totals = {variant.label: [0, 0] for variant in variants}
    for scenario in scenarios:
        cells = []
        for variant in variants:
            runs = [r for r in results if r.scenario == scenario and r.variant == variant.label]
            passed = sum(r.passed for r in runs)
            loaded = sum(any(s.startswith("python-") for s in r.skills_loaded) for r in runs)
            totals[variant.label][0] += passed
            totals[variant.label][1] += len(runs)
            cells.append(f"{passed}/{len(runs)} (skill {loaded}/{len(runs)})")
        print(f"{scenario:<22}" + "".join(f"{cell:>22}" for cell in cells))
    print(f"{'TOTAL':<22}" + "".join(f"{f'{p}/{n}':>22}" for p, n in totals.values()))
    cost = sum(result.cost_usd for result in results)
    print(f"\ncost: ${cost:.2f}")


def _self_test() -> int:
    broken: list[str] = []
    for scenario_dir in sorted(_SCENARIOS_ROOT.iterdir()):
        fixtures = scenario_dir / "fixtures"
        if not fixtures.is_dir():
            continue
        check = _load_check(scenario_dir.name)
        for fixture in sorted(fixtures.iterdir()):
            failures = check(fixture)
            expected_clean = fixture.name.startswith("good")
            if expected_clean == bool(failures):
                broken.append(f"{scenario_dir.name}/{fixture.name}: {[str(f) for f in failures]}")
    for line in broken:
        print(line)
    print("self-test:", "ok" if not broken else f"{len(broken)} broken")
    return _EXIT_OK if not broken else _EXIT_FAILED


def _parse_variant(text: str) -> _Variant:
    label, _, path = text.partition("=")
    if not label or not path:
        raise argparse.ArgumentTypeError(f"expected LABEL=PATH or LABEL={_NO_RULES}: {text}")
    if path == _NO_RULES:
        return _Variant(label=label, rules_root=None)
    root = Path(path).expanduser().resolve()
    if not (root / ".claude" / "rules" / "python").is_dir():
        raise argparse.ArgumentTypeError(f"{root} has no .claude/rules/python")
    return _Variant(label=label, rules_root=root)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", action="append", type=_parse_variant, default=[],
                        help=f"LABEL=PATH to a checkout with .claude/, or LABEL={_NO_RULES}")
    parser.add_argument("--scenario", action="append", default=[], help="run only these")
    parser.add_argument("--repeat", type=int, default=1, help="runs per scenario and variant")
    parser.add_argument("--jobs", type=int, default=4, help="sessions in parallel")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--self-test", action="store_true", help="run checks on fixtures only")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    return parser


def run(arguments: argparse.Namespace) -> int:
    if arguments.self_test:
        return _self_test()
    if not arguments.variant:
        print("at least one --variant is required", file=sys.stderr)
        return _EXIT_USAGE
    available = sorted(path.name for path in _SCENARIOS_ROOT.iterdir() if (path / "prompt.md").is_file())
    scenarios = arguments.scenario or available
    unknown = sorted(set(scenarios) - set(available))
    if unknown:
        print(f"unknown scenarios: {unknown}", file=sys.stderr)
        return _EXIT_USAGE
    plan = [(v, s, n) for v in arguments.variant for s in scenarios for n in range(1, arguments.repeat + 1)]
    if arguments.dry_run:
        for variant, scenario, attempt in plan:
            print(f"{variant.label} ({variant.rules_root or _NO_RULES}) {scenario} #{attempt}")
        return _EXIT_OK

    out = _RESULTS_ROOT / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with ThreadPoolExecutor(max_workers=arguments.jobs) as pool:
        futures = [
            pool.submit(_run_one, variant, scenario, attempt, model=arguments.model,
                        timeout_seconds=arguments.timeout_seconds, out=out)
            for variant, scenario, attempt in plan
        ]
        results = [future.result() for future in futures]
    (out / "summary.json").write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
    _print_table(results, arguments.variant)
    print(f"results: {out}")
    return _EXIT_OK if all(result.passed for result in results) else _EXIT_FAILED


def main() -> None:
    try:
        sys.exit(run(_build_parser().parse_args()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
