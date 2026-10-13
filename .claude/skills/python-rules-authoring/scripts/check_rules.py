#!/usr/bin/env python3
"""Check the Python rules and skills under ROOT against the conventions in python-rules-authoring.

ROOT is the directory holding `rules/python/` and `skills/` — `~/.claude`, or `.claude` in a
clone of the rules repository. Six checks, each reported as `path:line: message`:

- the budget, counted without front matter: the number of rules and the estimated tokens of the
  set loaded on every `.py` and of the set loaded on a test file, and the lines and estimated
  tokens of every `SKILL.md`;
- every `python` code block parses; an indented block is dedented first, and a block that is only
  `case` clauses is parsed inside a `match`;
- every `python-*` skill and every `*.md` file a document names in backticks or links exists;
- every `python-*` skill is named in `core.md` — a row in its map, or `/name` in its text;
- every `SKILL.md` has a `name` equal to its directory, a `description` and `paths`;
- a topic skill names a library skill only in a file's introduction, before its first heading
  below the title.

Exit codes: 0 clean, 1 findings, 2 ROOT does not hold the rules.
"""

import argparse
import ast
import re
import sys
import textwrap
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final

_EXIT_CLEAN: Final = 0
_EXIT_FOUND: Final = 1
_EXIT_ERROR: Final = 2
_EXIT_INTERRUPTED: Final = 130

# Close enough for English prose and code to set a ceiling by; a real tokenizer is not a dependency.
_CHARACTERS_PER_TOKEN: Final = 4
_SKILL_MAX_LINES: Final = 500
# Claude Code re-attaches the first 5,000 tokens of an invoked skill after compaction.
_SKILL_MAX_TOKENS: Final = 5_000
_SKILL_PREFIX: Final = "python-"
# The map's row for library skills names them without the prefix.
_LIBRARY_ROW_MARKER: Final = "`python-<library>`"
# Skills about the skills themselves, which name the others by design.
_META_SKILLS: Final = frozenset({"python-rules-authoring", "python-review"})
_SECTION_HEADING: Final = re.compile(r"^#{2,3} ")
# What a library's examples are written in; any other file shows the work against its own contracts.
_LIBRARY_API: Final[Mapping[str, re.Pattern[str]]] = MappingProxyType(
    {
        "python-sqlalchemy": re.compile(
            r"(?<![.\w])(AsyncSession|async_sessionmaker|sessionmaker|mapped_column|DeclarativeBase"
            r"|create_async_engine|create_engine|AsyncEngine|Mapped\[|select\()|(?<![.\w])Session\b"
        ),
        "python-persistence": re.compile(r"UnitOfWork|unit_of_work"),
        "python-pydantic": re.compile(
            r"\b(BaseModel|BaseSettings|ConfigDict|TypeAdapter|SecretStr|AwareDatetime|HttpUrl"
            r"|model_validate\w*|model_dump\w*)\b"
        ),
        "python-fastapi": re.compile(
            r"\b(FastAPI|APIRouter|HTTPException|JSONResponse)\b|Depends\("
        ),
        "python-niquests": re.compile(r"\b(niquests|httpx)\b"),
        "python-asyncpg": re.compile(r"\b(asyncpg|fetchrow|fetchval)\b"),
        "python-redis": re.compile(r"\bredis\.|\bRedis\b"),
        "python-cashews": re.compile(r"\bcashews\b|\bcache\.setup\b"),
        "python-faststream": re.compile(r"\b(faststream|RabbitBroker|RabbitRouter|AckPolicy)\b"),
        "python-tenacity": re.compile(r"\b(tenacity|stop_after_\w+|wait_random\w*)\b"),
        "python-orjson": re.compile(r"\borjson\b"),
        "python-pyjwt": re.compile(r"\bjwt\.|\bPyJWKClient\b"),
        "python-strawberry": re.compile(r"\bstrawberry\b"),
        "python-grpc": re.compile(r"\bgrpc\b|_pb2\b"),
        "python-alembic": re.compile(r"\balembic\b"),
    }
)
# A library built on another shows the other's API where the two meet, and nowhere else.
_LIBRARY_INTEGRATIONS: Final = frozenset(
    {
        ("python-alembic", "python-sqlalchemy"),
        ("python-cashews", "python-fastapi"),
        ("python-fastapi", "python-pydantic"),
        ("python-faststream", "python-fastapi"),
        ("python-faststream", "python-pydantic"),
        ("python-grpc", "python-fastapi"),
        ("python-grpc", "python-pydantic"),
        ("python-pydantic", "python-fastapi"),
        ("python-strawberry", "python-fastapi"),
        ("python-strawberry", "python-pydantic"),
    }
)
# A description says what the skill does and when to use it; the listing every session pays for
# is capped at 1% of the context window, so a description is a trigger, not a table of contents.
_DESCRIPTION_MAX_CHARACTERS: Final = 400
_DESCRIPTION_TRIGGER: Final = "Use when"
# A reference file's table of contents is part of its introduction.
_CONTENTS_HEADING: Final = "## Contents"
# The map's table rows are "| skill | when |"; the cell after the first pipe names the skills.
_LIBRARY_CELL_INDEX: Final = 2

# A fence is three or more backticks; it closes on a bare fence at least as long (CommonMark).
_FENCE: Final = re.compile(r"^\s*(`{3,})(\w*)\s*$")
# A rule is a `###` heading, or a top-level bold bullet in a file not yet in that format.
_RULE_LINE: Final = re.compile(r"^(### |- \*\*)")
_SKILL_REFERENCE: Final = re.compile(r"`(python-[a-z][a-z-]*)`")
_FILE_REFERENCE: Final = re.compile(r"`([\w-]+\.md)`|\]\(([\w./-]+\.md)\)")
_FRONT_MATTER_FIELD: Final = re.compile(r"^(\w+):\s*(.*)$")


@dataclass(frozen=True, slots=True, kw_only=True)
class _LoadBudget:
    label: str
    sample: PurePosixPath
    max_rules: int
    max_tokens: int


_LOAD_BUDGETS: Final = (
    _LoadBudget(
        label="every .py",
        sample=PurePosixPath("src/package/module.py"),
        max_rules=120,
        max_tokens=28_000,
    ),
    _LoadBudget(
        label="a test file",
        sample=PurePosixPath("tests/unit/test_module.py"),
        max_rules=140,
        max_tokens=36_000,
    ),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Finding:
    path: Path
    line: int
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _CodeBlock:
    start_line: int
    end_line: int
    language: str
    body: tuple[str, ...]


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
        "root",
        type=Path,
        metavar="ROOT",
        help="directory holding rules/python and skills",
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
        print(
            f"error: {root} holds no rules/python and skills directories",
            file=sys.stderr,
        )
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
        *_layering_findings(rules_directory / "core.md", skill_files),
        *(
            finding
            for document in (*rules, *skill_files)
            for finding in _library_api_findings(document)
        ),
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
    for budget in _LOAD_BUDGETS:
        loaded = [rule for rule in rules if _loads_on(rule, budget.sample)]
        rule_count = sum(_rule_count(rule) for rule in loaded)
        token_count = sum(_token_estimate(rule) for rule in loaded)
        if rule_count > budget.max_rules:
            yield _Finding(
                path=rules[0].path.parent,
                line=0,
                message=f"{rule_count} rules load on {budget.label}, ceiling {budget.max_rules}",
            )
        if token_count > budget.max_tokens:
            yield _Finding(
                path=rules[0].path.parent,
                line=0,
                message=(
                    f"about {token_count} tokens load on {budget.label},"
                    f" ceiling {budget.max_tokens}"
                ),
            )

    for skill_file in skill_files:
        if skill_file.path.name == "SKILL.md":
            yield from _skill_budget_findings(skill_file)


def _skill_budget_findings(skill_file: _Document) -> Iterator[_Finding]:
    if skill_file.body_line_count > _SKILL_MAX_LINES:
        yield _Finding(
            path=skill_file.path,
            line=1,
            message=f"{skill_file.body_line_count} lines, ceiling {_SKILL_MAX_LINES}",
        )
    token_count = _token_estimate(skill_file)
    if token_count > _SKILL_MAX_TOKENS:
        yield _Finding(
            path=skill_file.path,
            line=1,
            message=f"about {token_count} tokens, ceiling {_SKILL_MAX_TOKENS}",
        )


def _rule_count(document: _Document) -> int:
    code_lines = _code_line_numbers(document.lines)
    return sum(
        1
        for line_number, line in enumerate(document.lines, start=1)
        if line_number >= document.body_start_line
        and line_number not in code_lines
        and _RULE_LINE.match(line)
    )


def _token_estimate(document: _Document) -> int:
    body = document.lines[document.body_start_line - 1 :]
    return sum(len(line) + 1 for line in body) // _CHARACTERS_PER_TOKEN


def _loads_on(rule: _Document, sample: PurePosixPath) -> bool:
    # A rule with no front matter loads in every session, so on every file as well.
    return not rule.front_matter or any(sample.full_match(glob) for glob in _path_globs(rule))


def _path_globs(document: _Document) -> Iterator[str]:
    is_in_paths = False
    for line in document.front_matter:
        field = _FRONT_MATTER_FIELD.match(line)
        if field is not None:
            is_in_paths = field.group(1) == "paths"
            if is_in_paths and field.group(2):
                yield field.group(2).strip("\"'")
        elif is_in_paths and line.strip().startswith("-"):
            yield line.strip().removeprefix("-").strip().strip("\"'")


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
    for block in _code_blocks(lines):
        if block.language == "python":
            yield block.start_line, textwrap.dedent("\n".join(block.body))


def _code_blocks(lines: Sequence[str]) -> Iterator[_CodeBlock]:
    opening: re.Match[str] | None = None
    start_line = 0
    body: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        fence = _FENCE.match(line)
        if opening is None:
            if fence is not None:
                opening, start_line, body = fence, line_number, []
            continue
        is_closing = (
            fence is not None
            and not fence.group(2)
            and len(fence.group(1)) >= len(opening.group(1))
        )
        if not is_closing:
            body.append(line)
            continue
        yield _CodeBlock(
            start_line=start_line,
            end_line=line_number,
            language=opening.group(2),
            body=tuple(body),
        )
        opening = None


def _code_line_numbers(lines: Sequence[str]) -> frozenset[int]:
    return frozenset(
        line_number
        for block in _code_blocks(lines)
        for line_number in range(block.start_line, block.end_line + 1)
    )


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
    # A fenced example illustrates a reference; it does not make one.
    code_lines = _code_line_numbers(document.lines)
    for line_number, line in enumerate(document.lines, start=1):
        if line_number in code_lines:
            continue
        for skill_name in _SKILL_REFERENCE.findall(line):
            if skill_name not in skill_names:
                yield _Finding(
                    path=document.path,
                    line=line_number,
                    message=f"no skill {skill_name}",
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


def _layering_findings(core_path: Path, skill_files: Sequence[_Document]) -> Iterator[_Finding]:
    library_skills = _library_skill_names(core_path.read_text(encoding="utf-8"))
    for document in skill_files:
        skill_name = document.path.parent.name
        if skill_name in library_skills or skill_name in _META_SKILLS:
            continue
        yield from _library_names_past_introduction(document, library_skills)


def _library_api_findings(document: _Document) -> Iterator[_Finding]:
    owner = document.path.parent.name
    if owner in _META_SKILLS:
        return
    for block in _code_blocks(document.lines):
        if block.language != "python":
            continue
        for offset, line in enumerate(block.body, start=1):
            for library, api in _LIBRARY_API.items():
                if (
                    owner != library
                    and (owner, library) not in _LIBRARY_INTEGRATIONS
                    and api.search(line)
                ):
                    yield _Finding(
                        path=document.path,
                        line=block.start_line + offset,
                        message=f"{library}'s API in another file's example; use a contract here",
                    )


def _library_skill_names(core_text: str) -> frozenset[str]:
    library_row = next((line for line in core_text.splitlines() if _LIBRARY_ROW_MARKER in line), "")
    cells = library_row.split("|")
    library_cell = cells[_LIBRARY_CELL_INDEX] if len(cells) > _LIBRARY_CELL_INDEX else ""
    return frozenset(
        f"{_SKILL_PREFIX}{name}" for name in re.findall(r"`([a-z][a-z0-9]*)`", library_cell)
    )


def _library_names_past_introduction(
    document: _Document, library_skills: frozenset[str]
) -> Iterator[_Finding]:
    code_lines = _code_line_numbers(document.lines)
    is_past_introduction = False
    for line_number, line in enumerate(document.lines, start=1):
        if line_number < document.body_start_line or line_number in code_lines:
            continue
        if _SECTION_HEADING.match(line) and line.strip() != _CONTENTS_HEADING:
            is_past_introduction = True
        if not is_past_introduction:
            continue
        for skill_name in _SKILL_REFERENCE.findall(line):
            if skill_name in library_skills:
                yield _Finding(
                    path=document.path,
                    line=line_number,
                    message=(
                        f"a topic skill names {skill_name} outside its introduction;"
                        " route to it there, once"
                    ),
                )


def _front_matter_findings(document: _Document) -> Iterator[_Finding]:
    fields = {
        match.group(1): match.group(2)
        for line in document.front_matter
        if (match := _FRONT_MATTER_FIELD.match(line)) is not None
    }
    if fields.get("name") != document.path.parent.name:
        yield _Finding(
            path=document.path,
            line=1,
            message="front matter name differs from the directory",
        )
    if "description" not in fields:
        yield _Finding(path=document.path, line=1, message="front matter has no description")
    else:
        yield from _description_findings(document)
    if "paths" not in fields:
        yield _Finding(path=document.path, line=1, message="front matter has no paths")


def _description_findings(document: _Document) -> Iterator[_Finding]:
    description = _description(document.front_matter)
    if len(description) > _DESCRIPTION_MAX_CHARACTERS:
        yield _Finding(
            path=document.path,
            line=1,
            message=(
                f"description is {len(description)} characters,"
                f" ceiling {_DESCRIPTION_MAX_CHARACTERS}"
            ),
        )
    if _DESCRIPTION_TRIGGER not in description:
        yield _Finding(
            path=document.path,
            line=1,
            message=f"description has no {_DESCRIPTION_TRIGGER!r} clause",
        )


def _description(front_matter: Sequence[str]) -> str:
    parts: list[str] = []
    is_in_description = False
    for line in front_matter:
        field = _FRONT_MATTER_FIELD.match(line)
        if field is not None:
            is_in_description = field.group(1) == "description"
            value = field.group(2).strip()
            if is_in_description and value not in {">-", ">", "|", "|-"}:
                parts.append(value.strip("\"'"))
        elif is_in_description:
            parts.append(line.strip())
    return " ".join(part for part in parts if part)


if __name__ == "__main__":
    main()
