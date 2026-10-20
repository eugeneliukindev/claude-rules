"""Hidden checks for heavy-decision: the file read is passed in, the grading rules are used directly."""

import ast
from pathlib import Path

import pytest

from resumes.app import build_service


def test_gate_summary_of_a_file(tmp_path: Path) -> None:
    resume = tmp_path / "cv.txt"
    resume.write_text("Senior Python developer", encoding="utf-8")
    summary = build_service().summarize(resume)
    assert (summary.grade, summary.words) == ("senior", 3)


def _imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return found


def test_design_reading_is_passed_in() -> None:
    assert "resumes.files.read_text_file" not in _imports(Path("resumes/service.py"))


def test_design_grading_is_used_directly() -> None:
    assert "resumes.grading.grade_of" in _imports(Path("resumes/service.py")), "the grading rules are the decision"
