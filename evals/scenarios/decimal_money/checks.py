"""Money is Decimal built from strings or ints; no amount ever passes through float."""

import ast
from pathlib import Path

from evalkit import Failure, call_name, missing_code, parse_workdir


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    if not any("Decimal" in module.source for module in modules):
        return [*failures, *missing_code("amounts are not Decimal")]

    for module in modules:
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Call) and call_name(node) == "float":
                failures.append(Failure(file=module.name, line=node.lineno, reason="float() on an amount"))
            elif isinstance(node, ast.Call) and call_name(node) == "Decimal" and _is_float_derived(node):
                failures.append(Failure(file=module.name, line=node.lineno, reason="Decimal built from a float"))
            elif isinstance(node, ast.BinOp) and _has_float_literal(node):
                failures.append(Failure(file=module.name, line=node.lineno, reason="float literal in arithmetic"))
    return failures


def _is_float_derived(call: ast.Call) -> bool:
    return any(
        _is_float_literal(child) or (isinstance(child, ast.Call) and call_name(child) == "float")
        for argument in call.args
        for child in ast.walk(argument)
    )


def _has_float_literal(operation: ast.BinOp) -> bool:
    return _is_float_literal(operation.left) or _is_float_literal(operation.right)


def _is_float_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, float)
