"""How senior a resume reads."""

from __future__ import annotations

import re

_GRADES = (
    ("lead", re.compile(r"\b(?:lead|principal|head\s+of)\b", re.IGNORECASE)),
    ("senior", re.compile(r"\b(?:senior|sr\.?)\b", re.IGNORECASE)),
    ("middle", re.compile(r"\b(?:middle|mid)\b", re.IGNORECASE)),
    ("junior", re.compile(r"\b(?:junior|jr\.?|intern)\b", re.IGNORECASE)),
)


def grade_of(text: str) -> str | None:
    """The highest grade the resume names, or `None`; slow on long resumes, since every rule scans the whole text."""
    return next((grade for grade, pattern in _GRADES if pattern.search(text)), None)
