"""A unit whose name needs "and" does two things: no function, method or class is named that way."""

import ast
import re
from pathlib import Path
from typing import Final

from evalkit import Failure, functions_in, missing_code, parse_workdir

_SNAKE_AND: Final = re.compile(r"(^|_)and(_|$)")
_CAMEL_AND: Final = re.compile(r"[a-z]And[A-Z]")


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    if not any(module.name.endswith("signup.py") for module in modules):
        return [*failures, *missing_code("signup.py was not written")]

    for module in modules:
        for function in functions_in(module.tree):
            if _SNAKE_AND.search(function.name.strip("_")):
                failures.append(Failure(file=module.name, line=function.lineno, reason=f"{function.name} does two things"))
        for node in ast.walk(module.tree):
            if isinstance(node, ast.ClassDef) and _CAMEL_AND.search(node.name):
                failures.append(Failure(file=module.name, line=node.lineno, reason=f"{node.name} does two things"))
    return failures
