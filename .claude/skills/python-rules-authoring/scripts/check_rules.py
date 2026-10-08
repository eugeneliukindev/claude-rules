#!/usr/bin/env python3
"""Check the Python rules and skills under ROOT against the conventions in python-rules-authoring.

ROOT is the directory holding `rules/python/` and `skills/` — `~/.claude`, or `.claude` in a
clone of the rules repository. Five checks, each reported as `path:line: message`:

- the line budget: every rule file, the set loaded on every `.py`, every `SKILL.md`, counted
  without front matter;
- every `python` code block parses; an indented block is dedented first, and a block that is only
  `case` clauses is parsed inside a `match`;
- every `python-*` skill and every `*.md` file a document names in backticks or links exists;
- every `python-*` skill is named in `core.md` — a row in its map, or `/name` in its text;
- every `SKILL.md` has a `name` equal to its directory and a `description`.

Exit codes: 0 clean, 1 findings, 2 ROOT does not hold the rules.
"""

import argparse
import ast
import re
import sys
import textwrap
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_EXIT_CLEAN: Final = 0
_EXIT_FOUND: Final = 1
_EXIT_ERROR: Final = 2
_EXIT_INTERRUPTED: Final = 130

_NAMING_RULE_MAX_LINES: Final = 300
_RULE_MAX_LINES: Final = 120
_EVERY_PY_MAX_LINES: Final = 800
_SKILL_MAX_LINES: Final = 500

_EVERY_PY_GLOB: Final = "**/*.py"
_SKILL_PREFIX: Final = "python-"
# The map's row for library skills names them without the prefix.
_LIBRARY_ROW_MARKER: Final = "`python-<library>`"

_FENCE: Final = re.compile(r"^(\s*)```(\w*)\s*$")
_SKILL_REFERENCE: Final = re.compile(r"`(python-[a-z][a-z-]*)`")
_FILE_REFERENCE: Final = re.compile(r"`([\w-]+\.md)`|\]\(([\w./-]+\.md)\)")
_FRONT_MATTER_FIELD: Final = re.compile(r"^(\w+):\s*(.*)$")


@dataclass(frozen=True, slots=True, kw_only=True)
class _Finding:
    path: Path
    line: int
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _Document:
    path: Path
    lines: tuple[str, ...]
    body_start_line: int
    front_matter: tuple[str, ...]

    @property
    def body_line_count(self) -> int:
        return len(self.lines) - self.body_start_line + 1


def main() -> None:
    """Parse the command line, run the checks, and exit with their code."""
    parser = argparse.ArgumentParser(description="Check the Python rules and skills.")
    parser.add_argument(
        "root", type=Path, metavar="ROOT", help="directory holding rules/python and skills"
    )
    arguments = parser.parse_args()
    root: Path = arguments.root

    try:
        exit_code = run(root=root)
    except KeyboardInterrupt:
        exit_code = _EXIT_INTERRUPTED
    sys.exit(exit_code)


def run(*, root: Path) -> int:
    """Print every finding under `root` and return the exit code."""
    rules_directory = root / "rules" / "python"
    skills_directory = root / "skills"
    if not rules_directory.is_dir() or not skills_directory.is_dir():
        print(f"error: {root} holds no rules/python and skills directories", file=sys.stderr)
        return _EXIT_ERROR

    rules = tuple(_read_document(path) for path in sorted(rules_directory.glob("*.md")))
    skill_directories = tuple(sorted(skills_directory.glob(f"{_SKILL_PREFIX}*/")))
    skill_files = tuple(
        _read_document(path)
        for directory in skill_directories
        for path in sorted(directory.rglob("*.md"))
        if not _is_hidden(path.relative_to(directory))
    )
    skill_names = frozenset(directory.name for directory in skill_directories)

    findings = [
        *_budget_findings(rules, skill_files),
        *(finding for document in (*rules, *skill_files) for finding in _code_findings(document)),
        *(
            finding
            for document in (*rules, *skill_files)
            for finding in _reference_findings(document, skill_names, rules_directory)
        ),
        *_map_findings(rules_directory / "core.md", skill_names),
        *(
            finding
            for document in skill_files
            if document.path.name == "SKILL.md"
            for finding in _front_matter_findings(document)
        ),
    ]
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.message}")
    return _EXIT_FOUND if findings else _EXIT_CLEAN


def _read_document(path: Path) -> _Document:
    lines = tuple(path.read_text(encoding="utf-8").splitlines())
    if not lines or lines[0] != "---":
        return _Document(path=path, lines=lines, body_start_line=1, front_matter=())
    closing_index = lines.index("---", 1)
    return _Document(
        path=path,
        lines=lines,
        body_start_line=closing_index + 2,
        front_matter=lines[1:closing_index],
    )


def _is_hidden(relative_path: Path) -> bool:
    return any(part.startswith(".") for part in relative_path.parts)


def _budget_findings(
    rules: Sequence[_Document], skill_files: Sequence[_Document]
) -> Iterator[_Finding]:
    for rule in rules:
        ceiling = _NAMING_RULE_MAX_LINES if rule.path.name == "naming.md" else _RULE_MAX_LINES
        if rule.body_line_count > ceiling:
            yield _Finding(
                path=rule.path,
                line=1,
                message=f"{rule.body_line_count} lines, ceiling {ceiling}",
            )

    every_py = [rule for rule in rules if _loads_on_every_py(rule)]
    every_py_line_count = sum(rule.body_line_count for rule in every_py)
    if every_py_line_count > _EVERY_PY_MAX_LINES:
        names = ", ".join(rule.path.name for rule in every_py)
        yield _Finding(
            path=every_py[0].path.parent,
            line=0,
            message=(
                f"{every_py_line_count} lines load on every .py ({names}), "
                f"ceiling {_EVERY_PY_MAX_LINES}"
            ),
        )

    for skill_file in skill_files:
        if skill_file.path.name == "SKILL.md" and skill_file.body_line_count > _SKILL_MAX_LINES:
            yield _Finding(
                path=skill_file.path,
                line=1,
                message=f"{skill_file.body_line_count} lines, ceiling {_SKILL_MAX_LINES}",
            )


def _loads_on_every_py(rule: _Document) -> bool:
    # A rule with no front matter loads in every session, so on every .py as well.
    return not rule.front_matter or any(
        line.strip().removeprefix("-").strip().strip("\"'") == _EVERY_PY_GLOB
        for line in rule.front_matter
    )


def _code_findings(document: _Document) -> Iterator[_Finding]:
    for start_line, source in _python_blocks(document.lines):
        error = _parse_error(source)
        if error is not None:
            yield _Finding(
                path=document.path,
                line=start_line + (error.lineno or 1),
                message=f"python block does not parse: {error.msg}",
            )


def _python_blocks(lines: Sequence[str]) -> Iterator[tuple[int, str]]:
    block_lines: list[str] = []
    start_line = 0
    is_python = False
    is_inside = False
    for line_number, line in enumerate(lines, start=1):
        fence = _FENCE.match(line)
        if fence is None:
            if is_inside:
                block_lines.append(line)
            continue
        if not is_inside:
            is_inside = True
            is_python = fence.group(2) == "python"
            start_line = line_number
            block_lines = []
            continue
        is_inside = False
        if is_python:
            yield start_line, textwrap.dedent("\n".join(block_lines))


def _parse_error(source: str) -> SyntaxError | None:
    try:
        ast.parse(source)
    except SyntaxError as error:
        if not source.lstrip().startswith("case "):
            return error
    else:
        return None
    # A block of bare `case` clauses shows patterns; it parses as the body of a `match`.
    try:
        ast.parse("match subject:\n" + textwrap.indent(source, "    "))
    except SyntaxError as error:
        return error
    return None


def _reference_findings(
    document: _Document, skill_names: frozenset[str], rules_directory: Path
) -> Iterator[_Finding]:
    for line_number, line in enumerate(document.lines, start=1):
        for skill_name in _SKILL_REFERENCE.findall(line):
            if skill_name not in skill_names:
                yield _Finding(
                    path=document.path, line=line_number, message=f"no skill {skill_name}"
                )
        for bare_name, linked_path in _FILE_REFERENCE.findall(line):
            reference = bare_name or linked_path
            candidates = (document.path.parent / reference, rules_directory / reference)
            if not any(candidate.is_file() for candidate in candidates):
                yield _Finding(path=document.path, line=line_number, message=f"no file {reference}")


def _map_findings(core_path: Path, skill_names: frozenset[str]) -> Iterator[_Finding]:
    core_text = core_path.read_text(encoding="utf-8")
    library_row = next((line for line in core_text.splitlines() if _LIBRARY_ROW_MARKER in line), "")
    for skill_name in sorted(skill_names):
        library_name = skill_name.removeprefix(_SKILL_PREFIX)
        is_named = f"`{skill_name}`" in core_text or f"`/{skill_name}`" in core_text
        if not is_named and f"`{library_name}`" not in library_row:
            yield _Finding(path=core_path, line=1, message=f"{skill_name} is not named in core.md")


def _front_matter_findings(document: _Document) -> Iterator[_Finding]:
    fields = {
        match.group(1): match.group(2)
        for line in document.front_matter
        if (match := _FRONT_MATTER_FIELD.match(line)) is not None
    }
    if fields.get("name") != document.path.parent.name:
        yield _Finding(
            path=document.path, line=1, message="front matter name differs from the directory"
        )
    if "description" not in fields:
        yield _Finding(path=document.path, line=1, message="front matter has no description")


if __name__ == "__main__":
    main()
