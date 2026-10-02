from sqlalchemy import ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, selectinload


class Base(DeclarativeBase):
    pass


class Author(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    books: Mapped[list["Book"]] = relationship(back_populates="author", lazy="raise")


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"))
    author: Mapped[Author] = relationship(back_populates="books", lazy="raise_on_sql")


def list_authors_with_titles(session: Session) -> list[tuple[str, list[str]]]:
    authors = session.scalars(select(Author).options(selectinload(Author.books))).all()
    return [(author.name, [book.title for book in author.books]) for author in authors]
