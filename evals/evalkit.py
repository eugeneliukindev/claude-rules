"""Shared helpers for scenario checks: the failure record and AST access to produced code."""

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_SKIPPED_DIRECTORIES: Final = frozenset({"__pycache__", "venv", "site-packages", "node_modules"})


@dataclass(frozen=True, slots=True, kw_only=True)
class Failure:
    """One violation of the rule a scenario targets."""

    file: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.reason}"


@dataclass(frozen=True, slots=True, kw_only=True)
class Module:
    """A parsed Python file of the produced workdir."""

    name: str
    tree: ast.Module
    source: str


def iter_modules(workdir: Path) -> Iterator[Module | Failure]:
    """Yield every Python file under the workdir parsed, or a failure for one that does not parse."""
    for path in sorted(workdir.rglob("*.py")):
        relative = path.relative_to(workdir)
        if any(part.startswith(".") or part in _SKIPPED_DIRECTORIES for part in relative.parts):
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(relative))
        except SyntaxError as error:
            yield Failure(file=str(relative), line=error.lineno or 0, reason="does not parse")
            continue
        yield Module(name=str(relative), tree=tree, source=source)


def parse_workdir(workdir: Path) -> tuple[list[Module], list[Failure]]:
    """Split the workdir into parsed modules and parse failures."""
    modules: list[Module] = []
    failures: list[Failure] = []
    for item in iter_modules(workdir):
        if isinstance(item, Failure):
            failures.append(item)
        else:
            modules.append(item)
    return modules, failures


def dotted_name(node: ast.expr) -> str:
    """Return `a.b.c` for a name or attribute chain, and an empty string for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else ""
    return ""


def call_name(call: ast.Call) -> str:
    """Return the last segment of the called name: `uuid4` for `uuid.uuid4()`."""
    return dotted_name(call.func).rsplit(".", 1)[-1]


def keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    """Return the expression passed as keyword `name`, if any."""
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def is_constant(node: ast.expr | None, *values: object) -> bool:
    """Tell whether the node is a literal equal to one of the values."""
    return isinstance(node, ast.Constant) and node.value in values


def calls_in(node: ast.AST) -> Iterator[ast.Call]:
    """Yield every call expression inside the node, the node included."""
    return (child for child in ast.walk(node) if isinstance(child, ast.Call))


def functions_in(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield every function and method definition in the tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def missing_code(reason: str) -> list[Failure]:
    """Report that the produced code lacks what the scenario needs in order to be judged."""
    return [Failure(file="-", line=0, reason=reason)]
