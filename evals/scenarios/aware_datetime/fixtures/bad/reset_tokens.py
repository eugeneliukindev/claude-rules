import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class ResetToken:
    token: str
    user_id: int
    expires_at: datetime


def issue_reset_token(user_id: int) -> ResetToken:
    return ResetToken(secrets.token_urlsafe(32), user_id, datetime.now() + timedelta(minutes=30))


def is_expired(token: ResetToken) -> bool:
    return datetime.utcnow() >= token.expires_at
