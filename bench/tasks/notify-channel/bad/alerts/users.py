"""The people alerts go to."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

type Channel = Literal["email", "sms"]


@dataclass(frozen=True, slots=True, kw_only=True)
class User:
    """A user who receives alerts, by the channel they chose."""

    id: int
    email: str
    phone: str | None = None
    channel: Channel = "email"
