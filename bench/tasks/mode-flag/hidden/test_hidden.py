"""Hidden checks for mode-flag: CSV works, and no function branches on a format name."""

import ast
import csv
import inspect
import io
from pathlib import Path

from reports.model import Report, Row

REPORT = Report(period="2026-10", rows=(Row(product="tea", units=3, revenue=12.0), Row(product="mug", units=1, revenue=8.5)))


def _csv_text() -> str:
    import reports.export as module

    for name, function in inspect.getmembers(module, inspect.isfunction):
        if "csv" in name.lower() and not name.startswith("_"):
            return function(REPORT)
    for name in ("export",):
        function = getattr(module, name)
        for arguments in ((REPORT, "csv"),):
            try:
                return function(*arguments)
            except TypeError:
                pass
        for keyword in ("format", "fmt", "kind", "as_", "output"):
            try:
                return function(REPORT, **{keyword: "csv"})
            except TypeError:
                continue
    raise AssertionError("no way to export CSV")


def test_gate_csv_has_the_rows() -> None:
    cells = {cell for row in csv.reader(io.StringIO(_csv_text())) for cell in row}
    assert {"tea", "mug", "3", "8.5"} <= cells


def test_gate_json_still_works() -> None:
    import json

    from reports.export import export

    assert json.loads(export(REPORT))["period"] == "2026-10"


def test_design_no_branch_on_a_format_name() -> None:
    tree = ast.parse(Path("reports/export.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and str(side.value).lower() in {"csv", "json"}:
                    raise AssertionError(f"branches on a format name: {ast.unparse(node)}")
        if isinstance(node, ast.match_case) and any(
            word in ast.unparse(node.pattern).lower() for word in ("csv", "json")
        ):
            raise AssertionError("matches on a format name")


def test_design_export_keeps_its_signature() -> None:
    import inspect as _inspect

    from reports.export import export

    assert list(_inspect.signature(export).parameters) == ["report"], "export grew a mode parameter"
