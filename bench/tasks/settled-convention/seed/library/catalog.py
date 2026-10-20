"""What the library owns."""

from __future__ import annotations

from library.books import Book, BookRepo


class CatalogService:
    """Adds books to the catalogue and finds them."""

    def __init__(self, *, books: BookRepo) -> None:
        self._books = books

    def add(self, book_id: int, title: str) -> None:
        """Put a new book on the shelves."""
        self._books.put(Book(id=book_id, title=title))

    def find(self, book_id: int) -> Book | None:
        """The book with this id, or `None`."""
        return self._books.get(book_id)
