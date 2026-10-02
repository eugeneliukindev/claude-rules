import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

RESET_TOKEN_LIFETIME = timedelta(minutes=30)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResetToken:
    token: str
    user_id: int
    expires_at: datetime


def issue_reset_token(user_id: int, now: datetime) -> ResetToken:
    return ResetToken(token=secrets.token_urlsafe(32), user_id=user_id, expires_at=now + RESET_TOKEN_LIFETIME)


def is_expired(token: ResetToken) -> bool:
    return datetime.now(tz=UTC) >= token.expires_at
