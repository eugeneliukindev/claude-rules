"""Books on the shelves."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Book:
    """A book the library owns."""

    id: int
    title: str


class BookRepo:
    """Books kept in memory."""

    def __init__(self) -> None:
        self._books: dict[int, Book] = {}

    def get(self, book_id: int) -> Book | None:
        """The book with this id, or `None`."""
        return self._books.get(book_id)

    def put(self, book: Book) -> None:
        """Store `book`, replacing one with the same id."""
        self._books[book.id] = book
