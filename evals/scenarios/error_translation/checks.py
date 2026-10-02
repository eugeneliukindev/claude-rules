"""Errors are caught narrowly, translated with their cause, and never returned as a value."""

import ast
from pathlib import Path
from typing import Final

from evalkit import Failure, dotted_name, missing_code, parse_workdir

_BROAD: Final = frozenset({"Exception", "BaseException"})


def _caught_names(handler: ast.ExceptHandler) -> list[str]:
    if handler.type is None:
        return [""]
    if isinstance(handler.type, ast.Tuple):
        return [dotted_name(element) for element in handler.type.elts]
    return [dotted_name(handler.type)]


def _handler_failures(module_name: str, handler: ast.ExceptHandler) -> list[Failure]:
    failures: list[Failure] = []
    caught = _caught_names(handler)
    if any(name.rsplit(".", 1)[-1] in _BROAD or not name for name in caught):
        failures.append(Failure(file=module_name, line=handler.lineno, reason="broad except"))
    for node in ast.walk(handler):
        if isinstance(node, ast.Return):
            failures.append(Failure(file=module_name, line=node.lineno, reason="error returned as a value"))
        if isinstance(node, ast.Raise) and node.exc is not None and node.cause is None:
            failures.append(Failure(file=module_name, line=node.lineno, reason="raised without `from`: cause lost"))
    return failures


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    module = next((m for m in modules if m.name.endswith("customers.py")), None)
    if module is None:
        return [*failures, *missing_code("customers.py was not written")]
    handlers = [node for node in ast.walk(module.tree) if isinstance(node, ast.ExceptHandler)]
    if not handlers:
        return [*failures, *missing_code("no except clause: the 404 is never told apart")]
    for handler in handlers:
        failures.extend(_handler_failures(module.name, handler))
    return failures
