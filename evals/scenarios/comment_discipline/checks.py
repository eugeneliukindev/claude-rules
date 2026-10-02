"""Comments are one line, and neither comments nor docstrings refer to callers or ordering."""

import ast
import io
import re
import tokenize
from pathlib import Path
from typing import Final

from evalkit import Failure, missing_code, parse_workdir

_MAX_COMMENT_BLOCK_LINES: Final = 3
_NONLOCAL: Final = re.compile(
    r"\b(called|used|invoked) (by|from)\b|\bcallers?\b|\bmust (run|be called) (before|after)\b",
    re.IGNORECASE,
)


def _comment_failures(module_name: str, source: str) -> list[Failure]:
    failures: list[Failure] = []
    block_start, block_length, previous_line = 0, 0, -1
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        line = token.start[0]
        if _NONLOCAL.search(token.string):
            failures.append(Failure(file=module_name, line=line, reason="comment refers to a caller or an ordering"))
        if token.line[: token.start[1]].strip():
            continue  # a trailing comment on a code line is a reason, not a block
        if line == previous_line + 1:
            block_length += 1
        else:
            block_start, block_length = line, 1
        if block_length == _MAX_COMMENT_BLOCK_LINES + 1:
            failures.append(Failure(file=module_name, line=block_start, reason="comment block longer than three lines"))
        previous_line = line
    return failures


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    module = next((m for m in modules if m.name.endswith("shipping.py")), None)
    if module is None:
        return [*failures, *missing_code("shipping.py was not written")]
    failures.extend(_comment_failures(module.name, module.source))
    for node in ast.walk(module.tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module):
            docstring = ast.get_docstring(node) or ""
            if _NONLOCAL.search(docstring):
                line = getattr(node, "lineno", 1)
                failures.append(Failure(file=module.name, line=line, reason="docstring refers to a caller"))
    return failures
