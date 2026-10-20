"""Builds the resume services."""

from __future__ import annotations

from resumes.files import read_text_file
from resumes.service import ResumeService


def build_service() -> ResumeService:
    """A service reading resumes from disk."""
    return ResumeService(read=read_text_file)
