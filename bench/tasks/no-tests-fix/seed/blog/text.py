"""Text helpers for posts."""

from __future__ import annotations

import re

_NOT_SLUG = re.compile(r"[^a-z]+")


def slugify(title: str) -> str:
    """The URL part of a post's title: lower case words joined by dashes."""
    return _NOT_SLUG.sub("-", title.lower()).strip("-")
