#!/usr/bin/env python3
"""List top-level public names that no other module under ROOT uses, so each can take an `_`.

A name counts as used when another module mentions it as a name, an attribute, an imported name
or an identifier inside a string literal — forward references and patch targets included,
docstrings and comments not. Names a module lists in `__all__`, dunders, `main`, `run` and
`logger`, and the tests pytest collects by name are not candidates.

A function or class behind a decorator that may register it — a route, a CLI command, a fixture —
has a caller no search can see. Those are listed after the findings, marked, and do not fail the
run on their own.

Exit codes: 0 nothing found, 1 names found, 2 ROOT is not a directory or a module does not parse.
"""

import argparse
import ast
import re
import sys
from collections import defaultdict
from collections.abc import Container, Iterator, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Final

_EXIT_CLEAN: Final = 0
_EXIT_FOUND: Final = 1
_EXIT_ERROR: Final = 2
_EXIT_INTERRUPTED: Final = 130

# The CLI entry pair and the module logger are public by convention, whoever calls them.
_CONVENTIONAL_NAMES: Final = frozenset({"main", "run", "logger"})
_PYTEST_PREFIXES: Final = ("test", "Test")

# Decorators that describe or wrap a definition without handing it to a hidden caller.
_TRANSPARENT_DECORATORS: Final = frozenset(
    {
        "asynccontextmanager",
        "cache",
        "contextmanager",
        "dataclass",
        "dataclass_transform",
        "deprecated",
        "final",
        "lru_cache",
        "overload",
        "override",
        "runtime_checkable",
        "singledispatch",
        "total_ordering",
        "unique",
        "wraps",
    },
)

_IDENTIFIER: Final = re.compile(r"[A-Za-z_]\w*")


@dataclass(frozen=True, slots=True, kw_only=True)
class _Definition:
    path: Path
    line: int
    name: str
    is_registered: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class _ParsedModule:
    path: Path
    definitions: tuple[_Definition, ...]
    used_names: frozenset[str]


def main() -> None:
    """Parse the command line, run the check, and exit with its code."""
    parser = argparse.ArgumentParser(
        description="List top-level public names no other module uses.",
    )
    parser.add_argument("root", type=Path, metavar="ROOT", help="directory to scan")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="skip files whose path relative to ROOT matches; repeatable",
    )
    arguments = parser.parse_args()
    root: Path = arguments.root
    exclude_globs: list[str] = arguments.exclude

    try:
        exit_code = run(root=root, exclude_globs=exclude_globs)
    except KeyboardInterrupt:
        exit_code = _EXIT_INTERRUPTED
    sys.exit(exit_code)


def run(*, root: Path, exclude_globs: Sequence[str]) -> int:
    """Print every unused public name under `root` and return the exit code."""
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return _EXIT_ERROR

    modules: list[_ParsedModule] = []
    has_unparsable = False
    for path in _module_paths(root, exclude_globs):
        try:
            modules.append(_parse_module(path))
        except (SyntaxError, ValueError) as error:
            print(f"error: {path}: cannot parse: {error}", file=sys.stderr)
            has_unparsable = True
    if has_unparsable:
        return _EXIT_ERROR

    users = _users_by_name(modules)
    unused = [
        definition
        for module in modules
        for definition in module.definitions
        if not users.get(definition.name, frozenset()) - {definition.path}
    ]
    for definition in unused:
        if not definition.is_registered:
            print(f"{definition.path}:{definition.line}: {definition.name}")
    for definition in unused:
        if definition.is_registered:
            print(
                f"{definition.path}:{definition.line}: {definition.name} (decorated: unverifiable)"
            )

    is_clean = all(definition.is_registered for definition in unused)
    return _EXIT_CLEAN if is_clean else _EXIT_FOUND


def _module_paths(root: Path, exclude_globs: Sequence[str]) -> Iterator[Path]:
    for directory, subdirectories, files in root.walk():
        # Pruned in place, which is how walk() is told not to descend: hidden and cache trees.
        subdirectories[:] = sorted(
            name for name in subdirectories if not name.startswith(".") and name != "__pycache__"
        )
        for name in sorted(files):
            path = directory / name
            if path.suffix == ".py" and not _is_excluded(path.relative_to(root), exclude_globs):
                yield path


def _is_excluded(relative_path: Path, exclude_globs: Sequence[str]) -> bool:
    return any(fnmatch(relative_path.as_posix(), glob) for glob in exclude_globs)


def _parse_module(path: Path) -> _ParsedModule:
    tree = ast.parse(path.read_bytes(), filename=str(path))
    exported = _exported_names(tree)
    definitions = tuple(
        definition
        for definition in _definitions(tree, path)
        if _is_candidate(definition.name, exported, path)
    )
    return _ParsedModule(path=path, definitions=definitions, used_names=_used_names(tree))


def _definitions(tree: ast.Module, path: Path) -> Iterator[_Definition]:
    for statement in tree.body:
        match statement:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                yield _Definition(
                    path=path,
                    line=statement.lineno,
                    name=statement.name,
                    is_registered=_is_registered(statement.decorator_list),
                )
            case ast.Assign(targets=targets):
                for target in targets:
                    for name in _bound_names(target):
                        yield _Definition(
                            path=path, line=name.lineno, name=name.id, is_registered=False
                        )
            case ast.AnnAssign(target=ast.Name() as name) | ast.TypeAlias(name=ast.Name() as name):
                yield _Definition(path=path, line=name.lineno, name=name.id, is_registered=False)
            case _:
                # Imports bind names without defining them; nested blocks are not scanned.
                continue


def _bound_names(target: ast.expr) -> Iterator[ast.Name]:
    match target:
        case ast.Name():
            yield target
        case ast.Tuple(elts=elements) | ast.List(elts=elements):
            for element in elements:
                yield from _bound_names(element)
        case ast.Starred(value=value):
            yield from _bound_names(value)
        case _:
            # An attribute or a subscript target changes an object, and binds no new name.
            return


def _is_registered(decorators: Sequence[ast.expr]) -> bool:
    return any(
        _decorator_name(decorator) not in _TRANSPARENT_DECORATORS for decorator in decorators
    )


def _decorator_name(decorator: ast.expr) -> str:
    match decorator:
        case ast.Call(func=function):
            return _decorator_name(function)
        case ast.Name(id=name) | ast.Attribute(attr=name):
            return name
        case _:
            return ast.unparse(decorator)


def _is_candidate(name: str, exported: Container[str], path: Path) -> bool:
    return not (
        name.startswith("_")
        or name in exported
        or name in _CONVENTIONAL_NAMES
        or _is_collected_by_pytest(name, path)
    )


def _is_collected_by_pytest(name: str, path: Path) -> bool:
    is_test_module = path.name.startswith("test_") or path.stem.endswith("_test")
    return (is_test_module or path.name == "conftest.py") and name.startswith(_PYTEST_PREFIXES)


def _exported_names(tree: ast.Module) -> frozenset[str]:
    for statement in tree.body:
        match statement:
            case ast.Assign(
                targets=[ast.Name(id="__all__")], value=ast.List() | ast.Tuple() as value
            ):
                return frozenset(_string_elements(value))
            case ast.AnnAssign(
                target=ast.Name(id="__all__"), value=ast.List() | ast.Tuple() as value
            ):
                return frozenset(_string_elements(value))
            case _:
                continue
    return frozenset()


def _string_elements(sequence: ast.List | ast.Tuple) -> Iterator[str]:
    for element in sequence.elts:
        match element:
            case ast.Constant(value=str() as text):
                yield text
            case _:
                # `__all__` is written out as literals; anything computed exports nothing here.
                continue


def _used_names(tree: ast.Module) -> frozenset[str]:
    # Docstrings and other bare string statements are prose, not references.
    bare_expression_ids = frozenset(
        id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr)
    )
    names: set[str] = set()
    for node in ast.walk(tree):
        match node:
            case ast.Name(id=name) | ast.Attribute(attr=name):
                names.add(name)
            case ast.alias(name=dotted_name):
                names.update(dotted_name.split("."))
            case ast.Constant(value=str() as text) if id(node) not in bare_expression_ids:
                names.update(_IDENTIFIER.findall(text))
            case _:
                continue
    return frozenset(names)


def _users_by_name(modules: Sequence[_ParsedModule]) -> Mapping[str, frozenset[Path]]:
    users: defaultdict[str, set[Path]] = defaultdict(set)
    for module in modules:
        for name in module.used_names:
            users[name].add(module.path)
    return {name: frozenset(paths) for name, paths in users.items()}


if __name__ == "__main__":
    main()
