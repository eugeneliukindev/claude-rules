"""Who may borrow."""

from __future__ import annotations

from library.members import Member, MemberRepo


class MembershipService:
    """Signs members up and finds them."""

    def __init__(self, *, members: MemberRepo) -> None:
        self._members = members

    def join(self, member_id: int, name: str) -> None:
        """Give someone a library card."""
        self._members.put(Member(id=member_id, name=name))

    def find(self, member_id: int) -> Member | None:
        """The member with this id, or `None`."""
        return self._members.get(member_id)
