from unittest.mock import MagicMock

from registration import RegistrationService


def test_register_sends_welcome(mocker) -> None:
    repository = MagicMock()
    repository.exists.return_value = False
    mailer = MagicMock()
    mocker.patch("registration.User")

    RegistrationService(repository, mailer).register("a@example.com")

    mailer.send_welcome.assert_called_once()
