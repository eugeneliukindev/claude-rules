"""A private helper earns its interface: none is a one-call-site wrapper, stage or prose holder."""

import ast
from pathlib import Path
from typing import Final

from evalkit import Failure, calls_in, missing_code, parse_workdir

_STAGE_PREFIXES: Final = ("_log_", "_step", "_after_", "_before_", "_finish", "_handle_")
_PREDICATE_PREFIXES: Final = ("_is_", "_has_", "_can_", "_should_")


def _body_without_docstring(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        return body[1:]
    return body


def _shallow_reason(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = _body_without_docstring(function)
    docstring = ast.get_docstring(function) or ""
    body_lines = (body[-1].end_lineno or body[-1].lineno) - body[0].lineno + 1 if body else 0
    if function.name.startswith(_STAGE_PREFIXES):
        return "named for a stage, not an action"
    if docstring and len(docstring.splitlines()) > body_lines:
        return "docstring longer than the body"
    if function.name.startswith(_PREDICATE_PREFIXES):
        return ""  # a named predicate is an abstraction of its own
    if len(body) == 1 and isinstance(body[0], ast.Return | ast.Expr):
        return "body is a single expression: a rename, not an abstraction"
    return ""


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    module = next((m for m in modules if m.name.endswith("product_import.py")), None)
    if module is None:
        return [*failures, *missing_code("product_import.py was not written")]

    call_counts: dict[str, int] = {}
    for call in calls_in(module.tree):
        if isinstance(call.func, ast.Name):
            call_counts[call.func.id] = call_counts.get(call.func.id, 0) + 1
    for node in module.tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("_") or call_counts.get(node.name, 0) != 1:
            continue
        reason = _shallow_reason(node)
        if reason:
            failures.append(Failure(file=module.name, line=node.lineno, reason=f"{node.name}: {reason}"))
    return failures
