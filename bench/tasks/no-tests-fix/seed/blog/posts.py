"""Posts and their addresses."""

from __future__ import annotations

from blog.text import slugify


def post_url(title: str) -> str:
    """Where a post with this title lives."""
    return f"/posts/{slugify(title)}"
