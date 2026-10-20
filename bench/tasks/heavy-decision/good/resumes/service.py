"""What a resume says about its author."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from resumes.grading import grade_of


@dataclass(frozen=True, slots=True, kw_only=True)
class Summary:
    """A resume in two numbers."""

    grade: str | None
    words: int


class ResumeService:
    """Summarizes resumes; how a file is read is passed in."""

    def __init__(self, *, read: Callable[[Path], str]) -> None:
        self._read = read

    def summarize(self, path: Path) -> Summary:
        """The grade the resume names and its length in words."""
        text = self._read(path)
        return Summary(grade=grade_of(text), words=len(text.split()))
