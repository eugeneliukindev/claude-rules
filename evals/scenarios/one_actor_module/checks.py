"""Finance's pay rule and HR's hours report answer to different actors: separate modules, no shared helper."""

import ast
from pathlib import Path

from evalkit import Failure, call_name, calls_in, functions_in, missing_code, parse_workdir

type _Located = tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    located: list[_Located] = [(module.name, function) for module in modules for function in functions_in(module.tree)]
    pay = [(file, function) for file, function in located if _is_public_with(function, "pay")]
    report = [(file, function) for file, function in located if _is_public_with(function, "report")]
    if not pay or not report:
        return [*failures, *missing_code("no public pay function or no public report function")]

    for file in sorted({file for file, _ in pay} & {file for file, _ in report}):
        failures.append(Failure(file=file, line=0, reason="pay rules (finance) and hours report (HR) share a module"))

    defined = {function.name for _, function in located}
    shared = (_callees(pay) & _callees(report) & defined) - {function.name for _, function in pay + report}
    failures.extend(
        Failure(file=file, line=function.lineno, reason=f"{function.name} is shared by the pay rule and the HR report")
        for file, function in located
        if function.name in shared
    )
    return failures


def _is_public_with(function: ast.FunctionDef | ast.AsyncFunctionDef, word: str) -> bool:
    return not function.name.startswith("_") and word in function.name


def _callees(located: list[_Located]) -> set[str]:
    return {call_name(call) for _, function in located for call in calls_in(function)}
