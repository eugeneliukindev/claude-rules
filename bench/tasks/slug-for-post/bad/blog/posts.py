"""Blog posts and the store that keeps them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import count


def make_slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


@dataclass(frozen=True, slots=True, kw_only=True)
class Post:
    """A published post."""

    id: int
    title: str
    slug: str
    body: str


class PostStore:
    """Posts kept in memory, by id."""

    def __init__(self) -> None:
        self._posts: dict[int, Post] = {}
        self._ids = count(1)

    def create(self, title: str, body: str) -> Post:
        """Publish a post."""
        post = Post(id=next(self._ids), title=title, slug=make_slug(title), body=body)
        self._posts[post.id] = post
        return post

    def get(self, post_id: int) -> Post:
        """The post with `post_id`; `KeyError` when there is none."""
        return self._posts[post_id]

    def find_by_slug(self, slug: str) -> Post | None:
        for post in self._posts.values():
            if post.slug == slug:
                return post
        return None
