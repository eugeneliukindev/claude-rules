"""Registering a new user."""

from contracts import Mailer, User, UserRepository


class EmailTakenError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"Email {email} is already registered")
        self.email = email


class RegistrationService:
    def __init__(self, repository: UserRepository, mailer: Mailer) -> None:
        self._repository = repository
        self._mailer = mailer

    def register(self, email: str) -> User:
        normalized_email = email.strip().lower()
        if self._repository.exists(normalized_email):
            raise EmailTakenError(normalized_email)

        user = User(email=normalized_email)
        self._repository.add(user)
        self._mailer.send_welcome(user)
        return user
