"""One failing item stays one failure: the try sits inside the loop, around the per-item call."""

import ast
from collections.abc import Iterable, Set
from pathlib import Path
from typing import Final

from evalkit import Failure, call_name, calls_in, functions_in, missing_code, parse_workdir

_PER_ITEM_CALL: Final = "fetch_price"
_LOOPS: Final = (ast.For, ast.AsyncFor, ast.While)


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    functions = [function for module in modules for function in functions_in(module.tree)]
    per_item = {_PER_ITEM_CALL} | {function.name for function in functions if _calls(function.body, {_PER_ITEM_CALL})}
    guarded_helpers = {function.name for function in functions if _guards(function.body, {_PER_ITEM_CALL})}

    loops_found = 0
    for module in modules:
        for loop in ast.walk(module.tree):
            if not isinstance(loop, _LOOPS) or not _calls(loop.body, per_item):
                continue
            loops_found += 1
            if not (_guards(loop.body, per_item) or _calls(loop.body, guarded_helpers)):
                reason = f"{_PER_ITEM_CALL}() in a loop without a per-item try: one bad SKU stops the run"
                failures.append(Failure(file=module.name, line=loop.lineno, reason=reason))
    if not loops_found:
        return [*failures, *missing_code(f"no loop calls {_PER_ITEM_CALL}() per item")]
    return failures


def _calls(body: Iterable[ast.AST], names: Set[str]) -> bool:
    return any(call_name(call) in names for node in body for call in calls_in(node))


def _guards(body: Iterable[ast.AST], names: Set[str]) -> bool:
    return any(
        isinstance(node, ast.Try) and _calls(node.body, names) for statement in body for node in ast.walk(statement)
    )
