"""Builds the resume services."""

from __future__ import annotations

from resumes.service import ResumeService


def build_service() -> ResumeService:
    """A service reading resumes from disk."""
    return ResumeService()
