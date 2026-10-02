import pytest

from contracts import Mailer, User, UserRepository
from registration import EmailTakenError, RegistrationService


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self.users: list[User] = []

    def exists(self, email: str) -> bool:
        return any(user.email == email for user in self.users)

    def add(self, user: User) -> None:
        self.users.append(user)


class RecordingMailer(Mailer):
    def __init__(self) -> None:
        self.welcomed: list[User] = []

    def send_welcome(self, user: User) -> None:
        self.welcomed.append(user)


def test_register_rejects_taken_email() -> None:
    repository = InMemoryUserRepository()
    repository.add(User(email="a@example.com"))
    service = RegistrationService(repository, RecordingMailer())

    with pytest.raises(EmailTakenError, match="already registered"):
        service.register("A@example.com ")
