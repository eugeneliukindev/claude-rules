"""The grading half of run.py, without a model."""

import json
from pathlib import Path

import run


def _assistant_tool_use(name: str, tool_input: dict[str, str]) -> str:
    block = {"type": "tool_use", "name": name, "input": tool_input}
    return json.dumps({"type": "assistant", "message": {"content": [block]}})


def test_session_collects_skills_and_reads_from_the_stream() -> None:
    lines = [
        _assistant_tool_use("Skill", {"skill": "python-sync"}),
        _assistant_tool_use("Read", {"file_path": "/c/skills/python-sync/shutdown.md"}),
        json.dumps({"type": "result"}),
        "not json",
    ]

    session = run._session(lines)

    assert session.skills == frozenset({"python-sync"})
    assert session.reads == ("/c/skills/python-sync/shutdown.md",)


def test_checks_grade_skills_reads_and_code(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text("pool.shutdown(cancel_futures=True)\n", encoding="utf-8")
    case = {
        "skills": ["python-sync"],
        "not_skills": ["python-async"],
        "reads": ["shutdown.md"],
        "code": [
            {"files": "*.py", "match": r"cancel_futures=True"},
            {"files": "*.py", "no_match": r"daemon=True"},
            {"files": "*.py", "match": r"never written"},
        ],
    }
    session = run._Session(
        skills=frozenset({"python-sync", "python-async"}),
        reads=("/c/skills/python-sync/shutdown.md",),
    )

    checks = list(run._checks(case, session=session, working_directory=tmp_path, arm="with"))

    assert [check.passed for check in checks] == [True, False, True, True, True, False]


def test_without_arm_grades_the_code_only(tmp_path: Path) -> None:
    case = {"skills": ["python-sync"], "code": [{"files": "*.py", "no_match": "x"}]}
    session = run._Session(skills=frozenset(), reads=())

    checks = list(run._checks(case, session=session, working_directory=tmp_path, arm="without"))

    assert [check.passed for check in checks] == [True]
