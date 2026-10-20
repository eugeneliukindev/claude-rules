"""Resume files on disk."""

from __future__ import annotations

from pathlib import Path


def read_text_file(path: Path) -> str:
    """The text of a resume file."""
    return path.read_text(encoding="utf-8")
