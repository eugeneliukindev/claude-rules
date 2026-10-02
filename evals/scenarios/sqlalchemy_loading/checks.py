"""N+1 is an error, not a slowdown: relationships raise on lazy access and the query loads explicitly."""

from pathlib import Path
from typing import Final

from evalkit import Failure, call_name, calls_in, is_constant, keyword_value, missing_code, parse_workdir

_RAISING_STRATEGIES: Final = ("raise", "raise_on_sql")
_LOADER_OPTIONS: Final = frozenset({"selectinload", "joinedload", "subqueryload", "contains_eager", "immediateload"})


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    relationships = 0
    loads_explicitly = False
    for module in modules:
        for call in calls_in(module.tree):
            name = call_name(call)
            loads_explicitly = loads_explicitly or name in _LOADER_OPTIONS
            if name != "relationship":
                continue
            relationships += 1
            if not is_constant(keyword_value(call, "lazy"), *_RAISING_STRATEGIES):
                reason = 'relationship() without lazy="raise": unloaded access silently queries'
                failures.append(Failure(file=module.name, line=call.lineno, reason=reason))
    if not relationships:
        return [*failures, *missing_code("no relationship() defined")]
    if not loads_explicitly:
        failures.extend(missing_code("the query names no loader option such as selectinload"))
    return failures
