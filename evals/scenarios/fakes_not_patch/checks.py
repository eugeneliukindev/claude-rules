"""Unit tests inject fakes: no patching of the project's own modules, no mock without a spec."""

import ast
from pathlib import Path
from typing import Final

from evalkit import Failure, Module, call_name, calls_in, dotted_name, keyword_value, missing_code, parse_workdir

_MOCK_FACTORIES: Final = frozenset({"Mock", "MagicMock", "AsyncMock", "NonCallableMock", "NonCallableMagicMock"})
_SPEC_KEYWORDS: Final = ("spec", "spec_set")


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    tests = [module for module in modules if Path(module.name).name.startswith("test_")]
    if not tests:
        return [*failures, *missing_code("no test_*.py file written")]

    own_modules = {Path(module.name).stem for module in modules if module not in tests}
    for test in tests:
        own_names = own_modules | _names_imported_from(test, own_modules)
        for call in calls_in(test.tree):
            name = call_name(call)
            if name in _MOCK_FACTORIES and not any(keyword_value(call, key) for key in _SPEC_KEYWORDS):
                failures.append(Failure(file=test.name, line=call.lineno, reason=f"{name}() without spec="))
            elif name in {"patch", "object"} and _patches_own_code(call, own_names):
                failures.append(Failure(file=test.name, line=call.lineno, reason="patches the project's own code"))
    return failures


def _names_imported_from(test: Module, own_modules: set[str]) -> set[str]:
    return {
        alias.asname or alias.name
        for node in ast.walk(test.tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in own_modules
        for alias in node.names
    }


def _patches_own_code(call: ast.Call, own_names: set[str]) -> bool:
    if not call.args or "patch" not in dotted_name(call.func):
        return False
    target = call.args[0]
    if isinstance(target, ast.Constant) and isinstance(target.value, str):
        return target.value.split(".")[0] in own_names
    return dotted_name(target).split(".")[0] in own_names
