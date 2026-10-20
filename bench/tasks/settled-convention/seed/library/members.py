"""People who may borrow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Member:
    """Someone with a library card."""

    id: int
    name: str


class MemberRepo:
    """Members kept in memory."""

    def __init__(self) -> None:
        self._members: dict[int, Member] = {}

    def get(self, member_id: int) -> Member | None:
        """The member with this id, or `None`."""
        return self._members.get(member_id)

    def put(self, member: Member) -> None:
        """Store `member`, replacing one with the same id."""
        self._members[member.id] = member
