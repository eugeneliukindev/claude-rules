"""The people alerts go to."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class User:
    """A user who receives alerts."""

    id: int
    email: str
    phone: str | None = None
