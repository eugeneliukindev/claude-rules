"""Blog posts and the store that keeps them."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count

from blog.text import slugify


@dataclass(frozen=True, slots=True, kw_only=True)
class Post:
    """A published post."""

    id: int
    title: str
    slug: str
    body: str


class PostStore:
    """Posts kept in memory, by id and by slug."""

    def __init__(self) -> None:
        self._posts: dict[int, Post] = {}
        self._ids_by_slug: dict[str, int] = {}
        self._ids = count(1)

    def create(self, title: str, body: str) -> Post:
        """Publish a post under a slug of its title, numbered when the title is taken."""
        post_id = next(self._ids)
        slug = slugify(title)
        if slug in self._ids_by_slug:
            slug = f"{slug}-{post_id}"
        post = Post(id=post_id, title=title, slug=slug, body=body)
        self._posts[post.id] = post
        self._ids_by_slug[slug] = post.id
        return post

    def get(self, post_id: int) -> Post:
        """The post with `post_id`; `KeyError` when there is none."""
        return self._posts[post_id]

    def get_by_slug(self, slug: str) -> Post:
        """The post with `slug`; `KeyError` when there is none."""
        return self._posts[self._ids_by_slug[slug]]
