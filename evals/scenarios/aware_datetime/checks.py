"""Every datetime produced is timezone-aware; nothing reads the naive local clock."""

import ast
from pathlib import Path
from typing import Final

from evalkit import Failure, call_name, calls_in, dotted_name, is_constant, keyword_value, missing_code, parse_workdir

_ALWAYS_NAIVE: Final = frozenset({"utcnow", "utcfromtimestamp", "today"})
_NAIVE_WITHOUT_TZ: Final = frozenset({"now", "fromtimestamp"})
_TZ_POSITION: Final = {"now": 0, "fromtimestamp": 1}
_CLOCK_OWNERS: Final = frozenset({"datetime", "datetime.datetime", "date", "datetime.date"})


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    if not any("datetime" in module.source for module in modules):
        return [*failures, *missing_code("no datetime is used for the expiry")]

    for module in modules:
        for call in calls_in(module.tree):
            if dotted_name(call.func).rpartition(".")[0] not in _CLOCK_OWNERS:
                continue
            name = call_name(call)
            if name in _ALWAYS_NAIVE:
                failures.append(Failure(file=module.name, line=call.lineno, reason=f"{name}() returns a naive datetime"))
            elif name in _NAIVE_WITHOUT_TZ and _lacks_timezone(call, _TZ_POSITION[name]):
                failures.append(Failure(file=module.name, line=call.lineno, reason=f"{name}() without a timezone"))
    return failures


def _lacks_timezone(call: ast.Call, position: int) -> bool:
    timezone = keyword_value(call, "tz")
    if timezone is None and len(call.args) > position:
        timezone = call.args[position]
    return timezone is None or is_constant(timezone, None)
