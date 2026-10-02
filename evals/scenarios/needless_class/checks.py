"""A class is earned: no static-method box, no `__init__` plus one method, no stateless service."""

import ast
from pathlib import Path
from typing import Final

from evalkit import Failure, dotted_name, missing_code, parse_workdir

_EARNED_BASES: Final = frozenset({"Enum", "StrEnum", "IntEnum", "Exception", "ABC", "Protocol", "NamedTuple", "TypedDict"})


def _is_dataclass(node: ast.ClassDef) -> bool:
    return any("dataclass" in dotted_name(d.func if isinstance(d, ast.Call) else d) for d in node.decorator_list)


def _decorators(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    return {dotted_name(d.func if isinstance(d, ast.Call) else d).rsplit(".", 1)[-1] for d in function.decorator_list}


def _class_reason(node: ast.ClassDef) -> str:
    bases = {dotted_name(base).rsplit(".", 1)[-1] for base in node.bases}
    if bases & _EARNED_BASES or _is_dataclass(node):
        return ""
    methods = [item for item in node.body if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)]
    if not methods:
        return "a box for constants" if node.body else ""
    if all(_decorators(method) & {"staticmethod", "classmethod"} for method in methods):
        return "only static or class methods: a module already is that namespace"
    public = [method for method in methods if not method.name.startswith("_")]
    if any(method.name == "__init__" for method in methods) and len(public) == 1:
        return "`__init__` plus one method is a function"
    if not any(method.name == "__init__" for method in methods):
        return "stateless class with no dependencies"
    return ""


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    module = next((m for m in modules if m.name.endswith("pricing.py")), None)
    if module is None:
        return [*failures, *missing_code("pricing.py was not written")]
    for node in ast.walk(module.tree):
        if isinstance(node, ast.ClassDef):
            reason = _class_reason(node)
            if reason:
                failures.append(Failure(file=module.name, line=node.lineno, reason=f"{node.name}: {reason}"))
    return failures
