"""Every dataclass is frozen, slotted and keyword-only."""

import ast
from pathlib import Path
from typing import Final

from evalkit import Failure, dotted_name, is_constant, keyword_value, missing_code, parse_workdir

_REQUIRED_FLAGS: Final = ("frozen", "slots", "kw_only")


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    found = False
    for module in modules:
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if dotted_name(target).rsplit(".", 1)[-1] != "dataclass":
                    continue
                found = True
                missing = [flag for flag in _REQUIRED_FLAGS if not _sets_flag(decorator, flag)]
                if missing:
                    reason = f"dataclass {node.name} lacks {', '.join(f'{flag}=True' for flag in missing)}"
                    failures.append(Failure(file=module.name, line=node.lineno, reason=reason))
    if not found:
        return [*failures, *missing_code("no dataclass defined")]
    return failures


def _sets_flag(decorator: ast.expr, flag: str) -> bool:
    return isinstance(decorator, ast.Call) and is_constant(keyword_value(decorator, flag), True)
