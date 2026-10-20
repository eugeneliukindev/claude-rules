from library.app import build_catalog
from library.books import Book


def test_an_added_book_is_found() -> None:
    catalog = build_catalog()
    catalog.add(1, "Dune")
    assert catalog.find(1) == Book(id=1, title="Dune")
