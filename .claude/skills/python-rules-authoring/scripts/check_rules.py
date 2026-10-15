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
- a skill names another skill only in a file's introduction, before its first heading below the
  title;
- no example is written in a known library's API; the skills hold design, and a library's
  mechanics come from its current documentation;
- a function, class or constant defined in one skill's examples is defined in no other skill's,
  and in none of the rules';
- a skill is one `SKILL.md`, and any other `.md` file in it is reported.

Exit codes: 0 clean, 1 findings, 2 ROOT does not hold the rules.
"""

import argparse
import ast
import functools
import importlib
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
# Claude Code re-attaches about the first 5,000 tokens of an invoked skill after compaction;
# 6,000 leaves the tail of a one-file skill short.
_SKILL_MAX_TOKENS: Final = 6_000
_SKILL_PREFIX: Final = "python-"
# Skills about the skills themselves, which name the others by design.
_META_SKILLS: Final = frozenset({"python-rules-authoring", "python-review"})
_SECTION_HEADING: Final = re.compile(r"^#{2,3} ")
# Library APIs no example is written in: an example shows the work against its own contracts.
_LIBRARY_API: Final[Mapping[str, re.Pattern[str]]] = MappingProxyType(
    {
        "sqlalchemy": re.compile(
            r"(?<![.\w])(AsyncSession|async_sessionmaker|sessionmaker|mapped_column|DeclarativeBase"
            r"|create_async_engine|create_engine|AsyncEngine|Mapped\[|select\()|(?<![.\w])Session\b"
            r"|\.scalars?\(|\bengine\.|\(engine\)|\bas engine\b|\bengine\s*="
        ),
        "a unit of work": re.compile(r"UnitOfWork|unit_of_work"),
        "pydantic": re.compile(
            r"\b(BaseModel|BaseSettings|ConfigDict|TypeAdapter|SecretStr|AwareDatetime|HttpUrl"
            r"|model_validate\w*|model_dump\w*|model_copy|model_fields\w*|model_json_schema)\b"
        ),
        "fastapi": re.compile(r"\b(FastAPI|APIRouter|HTTPException|JSONResponse)\b|Depends\("),
        "niquests": re.compile(r"\b(niquests|httpx)\b"),
        "asyncpg": re.compile(r"\b(asyncpg|fetchrow|fetchval)\b"),
        "redis": re.compile(r"\bredis\.|\bRedis\b"),
        "cashews": re.compile(r"\bcashews\b|\bcache\.setup\b"),
        "faststream": re.compile(r"\b(faststream|RabbitBroker|RabbitRouter|AckPolicy)\b"),
        "tenacity": re.compile(r"\b(tenacity|stop_after_\w+|wait_random\w*)\b"),
        "orjson": re.compile(r"\borjson\b"),
        "pyjwt": re.compile(r"\bjwt\.|\bPyJWKClient\b"),
        "strawberry": re.compile(r"\bstrawberry\b"),
        "grpc": re.compile(r"\bgrpc\b|_pb2\b"),
        "alembic": re.compile(r"\balembic\b"),
    }
)
# A description says what the skill does and when to invoke it; the listing every session pays for
# is capped at 1% of the context window, so a description is a trigger, not a table of contents.
_DESCRIPTION_MAX_CHARACTERS: Final = 400
# The directive form activated in all of 650 trials, where "Use when" left the choice to the model:
# https://medium.com/@ivan.seleznov1/why-claude-code-skills-dont-activate-and-how-to-fix-it-86f679409af1
_DESCRIPTION_TRIGGER: Final = "ALWAYS invoke"
# What a CORRECT half shows is what the model copies, so it keeps the mechanical rules of every
# other rule: a constant is Final, a dataclass is frozen, slotted and keyword-only, and so on.
_EXAMPLE_MARKER: Final = re.compile(r"^# (WRONG|CORRECT)\b")
_CONSTANT_NAME: Final = re.compile(r"^_?[A-Z][A-Z0-9_]*[A-Z0-9]$")
_SETTING_NAME: Final = re.compile(
    r"(SECONDS|TTL|_MAX_|^_?MAX_|LIMIT|SIZE|BYTES|WINDOW|INTERVAL|ATTEMPTS|DEADLINE|TIMEOUT"
    r"|LIFETIME|MARGIN|CAPACITY|WORKERS|_PATH|PREFIX|WIDTH|LENGTH|HOURS|DAYS|DURATION|PERIOD"
    r"|DELAY|COUNT|DEPTH|BATCH|THRESHOLD|PRECISION|RETRYABLE)"
)
_FACTORY_NAME: Final = re.compile(r"^(build_|create_|make_|open_)")
_ROOT_NAMES: Final = frozenset({"main", "run", "lifespan"})
_TEST_PREFIX: Final = "test_"
_SCRIPTS_SKILL: Final = "python-scripts"
_IN_PLACE_DECORATORS: Final = (
    "fixture",
    ".get",
    ".post",
    ".put",
    ".patch",
    ".delete",
    ".websocket",
    ".route",
    "subscriber",
    "strawberry.",
)
_SETTING_MESSAGE: Final = "reads the setting"
_LIFETIME_DECORATORS: Final = frozenset({"contextmanager", "asynccontextmanager"})
_TEST_DOUBLE_PREFIXES: Final = ("InMemory", "Fake", "Recording", "Stub", "Broken")
_SETTINGS_TYPE: Final = re.compile(r"\b\w*Settings\b")
# Names a framework or the language fixes, which every skill may define.
_SHARED_DEFINITIONS: Final = frozenset(
    (
        "main lifespan upgrade downgrade Settings Base Query Mutation Subscription Context app "
        "client setup teardown "
    ).split()
)
_RULES_OWNER: Final = "rules"
# A bespoke name: CamelCase, or snake_case with an underscore; a lone lower-case word is vocabulary.
_BESPOKE_NAME: Final = re.compile(
    r"^(_?[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*|_?[a-z0-9]+(_[a-z0-9]+)+)$"
)
# Standard-library and library names an example may call without defining; everything else an
# example calls or constructs is its own, and belongs to one skill.
_STDLIB_MODULES: Final = tuple(
    (
        "builtins typing dataclasses contextlib functools asyncio collections collections.abc "
        "itertools datetime decimal pathlib json re logging enum abc hmac hashlib secrets uuid "
        "threading concurrent.futures queue subprocess signal os sys time argparse unittest.mock "
        "warnings textwrap urllib.request urllib.parse http ssl socket tempfile shutil csv io "
        "struct base64 random statistics math operator types weakref inspect importlib pickle copy "
        "string zoneinfo smtplib sqlite3 gzip zipfile tarfile heapq bisect multiprocessing pprint "
        "ipaddress fractions numbers selectors traceback unittest email html xml.etree.ElementTree "
        "configparser tomllib platform errno stat getpass locale gettext codecs binascii zlib lzma "
        "bz2 glob fnmatch shlex sched select mmap resource pwd grp ctypes "
    ).split()
)
_LIBRARY_NAMES: Final = frozenset(
    (
        "FastAPI APIRouter Depends HTTPException JSONResponse StreamingResponse Response "
        "Request WebSocket WebSocketDisconnect BackgroundTasks TestClient Query Body Header "
        "Cookie Form File UploadFile Security BaseModel BaseSettings SettingsConfigDict "
        "ConfigDict Field TypeAdapter ValidationError SecretStr AwareDatetime HttpUrl "
        "field_validator model_validator computed_field AsyncSession async_sessionmaker "
        "sessionmaker create_async_engine create_engine select insert update delete text "
        "mapped_column relationship selectinload joinedload func and_ or_ Redis ConnectionPool "
        "Retry NoBackoff ExponentialBackoff RabbitBroker RabbitRouter RabbitQueue "
        "RabbitExchange TestRabbitBroker Context Logger retry stop_after_attempt "
        "stop_after_delay wait_random_exponential wait_exponential_jitter wait_none "
        "retry_if_exception_type before_sleep_log PyJWKClient AsyncClient Session AsyncSession "
        "Timeout Cache op sa table column strawberry DataLoader GraphQLRouter Info Mock "
        "MagicMock AsyncMock create_autospec patch fixture mark raises param approx given "
        "settings st Channel Server ServicerContext StatusCode RpcError aio Timestamp Decimal "
        "Money Faker Counter Histogram get_meter get_tracer Status SpanKind NullHandler "
        "JsonFormatter orjson dumps loads uvicorn Config Process Thread ThreadPoolExecutor "
        "ProcessPoolExecutor TaskGroup Semaphore Queue Event Lock PriorityQueue LifoQueue "
        "ExitStack AsyncExitStack ContextVar NewType TypeVar ParamSpec Protocol "
        "runtime_checkable final override dataclass field replace asdict partial cache "
        "lru_cache cached_property wraps reduce deque defaultdict OrderedDict namedtuple Path "
        "PurePosixPath UUID uuid4 uuid7 datetime date timedelta timezone time ZoneInfo Enum "
        "StrEnum IntEnum Flag auto unique ABC abstractmethod Literal Annotated TypedDict "
        "NamedTuple Never NoReturn cast assert_never TYPE_CHECKING Self ClassVar Final Unpack "
        "Required NotRequired TypeIs TypeGuard Awaitable Coroutine Callable Iterator "
        "AsyncIterator Iterable AsyncIterable Generator AsyncGenerator Mapping MutableMapping "
        "Sequence MutableSequence Set MappingProxyType SimpleNamespace ArgumentParser Namespace "
        "BooleanOptionalAction HTTPStatus HTTPError URLError urlopen urlparse urljoin quote "
        "compare_digest token_urlsafe token_bytes sha256 pbkdf2_hmac scrypt getLogger "
        "basicConfig run sleep gather wait_for timeout create_task to_thread get_running_loop "
        "aclosing closing suppress contextmanager asynccontextmanager nullcontext "
        "redirect_stdout monotonic perf_counter getcontext localcontext ROUND_HALF_EVEN "
        "ROUND_HALF_UP ROUND_DOWN InvalidOperation dedent indent compile fullmatch match search "
        "sub escape IGNORECASE MULTILINE VERBOSE DOTALL signal SIGTERM SIGINT SIGHUP SIG_DFL "
        "Popen PIPE DEVNULL CalledProcessError TimeoutExpired check_output check_call "
    ).split()
)
_LEGACY_TYPING: Final = frozenset({"Optional", "Union", "List", "Dict", "Tuple", "Set", "Type"})
_NAIVE_NOW: Final = frozenset({"datetime.now", "datetime.utcnow", "date.today"})
_DATACLASS_FLAGS: Final = ("frozen=True", "slots=True", "kw_only=True")
# A reference file's table of contents is part of its introduction.
_CONTENTS_HEADING: Final = "## Contents"

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
        max_rules=100,
        max_tokens=22_000,
    ),
    _LoadBudget(
        label="a test file",
        sample=PurePosixPath("tests/unit/test_module.py"),
        max_rules=120,
        max_tokens=28_000,
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
        *_shared_definition_findings((*rules, *skill_files)),
        *(
            finding
            for document in (*rules, *skill_files)
            for finding in _library_api_findings(document)
        ),
        *(
            finding
            for document in (*rules, *skill_files)
            for finding in _example_findings(document)
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
        else:
            # The model opens a linked file in a minority of runs: a skill is its SKILL.md alone.
            yield _Finding(
                path=skill_file.path,
                line=1,
                message="a skill holds one SKILL.md; move this into it",
            )


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
    for skill_name in sorted(skill_names):
        if f"`{skill_name}`" not in core_text and f"`/{skill_name}`" not in core_text:
            yield _Finding(path=core_path, line=1, message=f"{skill_name} is not named in core.md")


def _layering_findings(core_path: Path, skill_files: Sequence[_Document]) -> Iterator[_Finding]:
    for document in skill_files:
        skill_name = document.path.parent.name
        if skill_name in _META_SKILLS:
            continue
        yield from _skill_names_past_introduction(document)




def _shared_definition_findings(documents: Sequence[_Document]) -> Iterator[_Finding]:
    # owner -> name -> first definition; the rules directory counts as one owner.
    first_by_owner: dict[str, dict[str, tuple[Path, int]]] = {}
    for document in documents:
        owner = _definition_owner(document)
        if owner in _META_SKILLS:
            continue
        definitions = first_by_owner.setdefault(owner, {})
        for block in _code_blocks(document.lines):
            if block.language != "python":
                continue
            try:
                tree = ast.parse(textwrap.dedent("\n".join(block.body)))
            except SyntaxError:
                continue
            for name, line in _defined_names(tree):
                definitions.setdefault(name, (document.path, block.start_line + line))
    owners_by_name: dict[str, list[str]] = {}
    for owner, definitions in first_by_owner.items():
        for name in definitions:
            owners_by_name.setdefault(name, []).append(owner)
    for name, owners in sorted(owners_by_name.items()):
        for owner in owners:
            others = [other for other in owners if other != owner]
            if not others:
                continue
            path, line = first_by_owner[owner][name]
            yield _Finding(
                path=path,
                line=line,
                message=f"{name} is also defined in {', '.join(sorted(others))}",
            )


def _definition_owner(document: _Document) -> str:
    if document.path.parent.name.startswith(_SKILL_PREFIX):
        return document.path.parent.name
    return _RULES_OWNER


def _defined_names(tree: ast.Module) -> Iterator[tuple[str, int]]:
    yield from _top_level_definitions(tree)
    known = _known_names()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id not in known
            and _BESPOKE_NAME.match(node.func.id)
        ):
            yield node.func.id, node.lineno


@functools.cache
def _known_names() -> frozenset[str]:
    names = set(_LIBRARY_NAMES) | set(_SHARED_DEFINITIONS)
    for module_name in _STDLIB_MODULES:
        try:
            names.update(dir(importlib.import_module(module_name)))
        except ImportError:
            continue
    return frozenset(names)


def _top_level_definitions(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and _CONSTANT_NAME.match(node.targets[0].id)
        ):
            name = node.targets[0].id
        else:
            continue
        if name.startswith("__") or name in _SHARED_DEFINITIONS:
            continue
        yield name, node.lineno


def _example_findings(document: _Document) -> Iterator[_Finding]:
    if document.path.parent.name in _META_SKILLS:
        return
    for block in _code_blocks(document.lines):
        if block.language != "python":
            continue
        source = _correct_half(block.body)
        try:
            tree = ast.parse(textwrap.dedent(source))
        except SyntaxError:
            continue
        for line, message in _example_violations(tree):
            # A script is run, not tested, so it reads its constants where it stands.
            if document.path.parent.name == _SCRIPTS_SKILL and _SETTING_MESSAGE in message:
                continue
            yield _Finding(
                path=document.path, line=block.start_line + line, message=f"CORRECT: {message}"
            )


def _correct_half(body: Sequence[str]) -> str:
    # WRONG lines become blank so the line numbers still point into the file.
    kept: list[str] = []
    is_wrong = False
    for line in body:
        marker = _EXAMPLE_MARKER.match(line)
        if marker is not None:
            is_wrong = marker.group(1) == "WRONG"
            kept.append("")
            continue
        kept.append("" if is_wrong else line)
    return "\n".join(kept)


def _example_violations(tree: ast.Module) -> Iterator[tuple[int, str]]:
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and _CONSTANT_NAME.match(node.targets[0].id)
        ):
            yield node.lineno, f"constant {node.targets[0].id} is not Final"
    for any_node in ast.walk(tree):
        yield from _node_violations(any_node)
    yield from _setting_violations(tree)


def _node_violations(node: ast.AST) -> Iterator[tuple[int, str]]:
    if isinstance(node, ast.ClassDef):
        for decorator in node.decorator_list:
            spelled = ast.unparse(decorator)
            if spelled.split("(")[0].removeprefix("dataclasses.") == "dataclass":
                missing = [flag for flag in _DATACLASS_FLAGS if flag not in spelled]
                if missing:
                    yield node.lineno, f"{node.name} lacks {', '.join(missing)}"
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield from _settings_parameters(node)
        defaults = [*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]
        if any(isinstance(default, (ast.List, ast.Dict, ast.Set)) for default in defaults):
            yield node.lineno, f"{node.name} has a mutable default"
    elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id in _LEGACY_TYPING:
            yield node.lineno, f"{node.value.id}[...] instead of the modern spelling"
    elif isinstance(node, ast.Call) and not node.args and not node.keywords:
        if ast.unparse(node.func) in _NAIVE_NOW:
            yield node.lineno, f"{ast.unparse(node.func)}() without a timezone"
    elif isinstance(node, ast.ExceptHandler) and node.type is None:
        yield node.lineno, "a bare except"


def _settings_parameters(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[tuple[int, str]]:
    # Only the entry point holds the settings object; everything below takes its fields.
    arguments = (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
    for argument in arguments:
        annotation = ast.unparse(argument.annotation) if argument.annotation else ""
        if _SETTINGS_TYPE.search(annotation):
            yield (
                function.lineno,
                f"{function.name} takes the settings object {argument.arg}; pass its fields",
            )


def _setting_violations(tree: ast.Module) -> Iterator[tuple[int, str]]:
    # A setting read inside a function or a method belongs in its signature, defaulted to the
    # constant; only the root, a test and a fixture read one where they stand.
    scopes: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _reads_in_place(node)
    ]
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ClassDef)
            and not node.name.startswith(_TEST_DOUBLE_PREFIXES)
            and not any("strawberry" in ast.unparse(decorator) for decorator in node.decorator_list)
        ):
            scopes.extend(
                member
                for member in node.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    for scope in scopes:
        defaults = {
            name.id
            for default in (*scope.args.defaults, *scope.args.kw_defaults)
            if default is not None
            for name in ast.walk(default)
            if isinstance(name, ast.Name)
        }
        for statement in scope.body:
            for name in ast.walk(statement):
                if (
                    isinstance(name, ast.Name)
                    and isinstance(name.ctx, ast.Load)
                    and name.id not in defaults
                    and _CONSTANT_NAME.match(name.id)
                    and _SETTING_NAME.search(name.id)
                ):
                    yield name.lineno, f"{scope.name} reads the setting {name.id}"


def _reads_in_place(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    # A framework parses a route's or a subscriber's signature: a defaulted parameter there is
    # an input the client sets, so the value stays in the body.
    return (
        function.name in _ROOT_NAMES
        or function.name.startswith(_TEST_PREFIX)
        or any(
            marker in ast.unparse(decorator)
            for decorator in function.decorator_list
            for marker in _IN_PLACE_DECORATORS
        )
    )


def _is_lifetime(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        ast.unparse(decorator).rsplit(".", 1)[-1] in _LIFETIME_DECORATORS
        for decorator in function.decorator_list
    )


def _library_api_findings(document: _Document) -> Iterator[_Finding]:
    owner = document.path.parent.name
    if owner in _META_SKILLS:
        return
    for block in _code_blocks(document.lines):
        if block.language != "python":
            continue
        for offset, line in enumerate(block.body, start=1):
            for library, api in _LIBRARY_API.items():
                if api.search(line):
                    yield _Finding(
                        path=document.path,
                        line=block.start_line + offset,
                        message=f"{library}'s API in an example; use a contract of the skill's own",
                    )


def _skill_names_past_introduction(document: _Document) -> Iterator[_Finding]:
    own_name = document.path.parent.name
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
            if skill_name != own_name:
                yield _Finding(
                    path=document.path,
                    line=line_number,
                    message=(
                        f"names {skill_name} outside the introduction; a skill stands alone,"
                        " and routes to a neighbour in its introduction, once"
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
