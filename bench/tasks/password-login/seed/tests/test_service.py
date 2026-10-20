from accounts.app import build_service


def test_unknown_email_has_no_account() -> None:
    assert build_service().find("nobody@example.com") is None
