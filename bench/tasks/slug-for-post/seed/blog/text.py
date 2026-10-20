"""Text helpers shared by the blog."""

from __future__ import annotations

import re
import unicodedata

_NOT_WORD = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, max_length: int = 60) -> str:
    """`text` as a lower-case ASCII slug of words joined by hyphens, at most `max_length` long."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = _NOT_WORD.sub("-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-")


def excerpt(text: str, *, words: int = 30) -> str:
    """The first `words` words of `text`."""
    return " ".join(text.split()[:words])
