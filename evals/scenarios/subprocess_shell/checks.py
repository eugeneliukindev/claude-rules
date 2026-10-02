"""A subprocess takes an argument list; no shell ever sees a value from outside."""

from pathlib import Path
from typing import Final

from evalkit import Failure, call_name, calls_in, dotted_name, is_constant, keyword_value, missing_code, parse_workdir

_ALWAYS_SHELL: Final = frozenset(
    {"os.system", "os.popen", "subprocess.getoutput", "subprocess.getstatusoutput", "create_subprocess_shell"}
)
_SPAWNERS: Final = frozenset({"run", "Popen", "call", "check_call", "check_output", "create_subprocess_exec"})


def check(workdir: Path) -> list[Failure]:
    modules, failures = parse_workdir(workdir)
    spawned = False
    for module in modules:
        for call in calls_in(module.tree):
            name = dotted_name(call.func)
            if name in _ALWAYS_SHELL or call_name(call) == "create_subprocess_shell":
                failures.append(Failure(file=module.name, line=call.lineno, reason=f"{name}() runs a shell string"))
                continue
            if call_name(call) not in _SPAWNERS:
                continue
            spawned = True
            shell = keyword_value(call, "shell")
            if shell is not None and not is_constant(shell, False):
                failures.append(Failure(file=module.name, line=call.lineno, reason=f"{name}() with shell=True"))
    if not spawned and not failures:
        return missing_code("no subprocess is started")
    return failures
