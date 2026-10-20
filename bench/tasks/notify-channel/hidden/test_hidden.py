"""Hidden checks for notify-channel: SMS works, and no shared unit branches on the channel name."""

import ast
from pathlib import Path

from alerts.gateways import SmsGateway, SmtpClient
from alerts.users import User


class FakeSmtp(SmtpClient):
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send_mail(self, to: str, subject: str, body: str) -> None:
        self.sent.append(to)


class FakeSms(SmsGateway):
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, phone: str, text: str) -> None:
        self.sent.append(phone)


def _service():
    from alerts.app import build_service

    smtp, sms = FakeSmtp(), FakeSms()
    return build_service(smtp, sms), smtp, sms


def test_gate_sms_user_gets_a_text() -> None:
    service, smtp, sms = _service()
    service.alert(User(id=1, email="a@example.com", phone="+100", channel="sms"), "disk full")
    assert sms.sent == ["+100"]
    assert smtp.sent == []


def test_gate_email_user_gets_mail() -> None:
    service, smtp, sms = _service()
    service.alert(User(id=2, email="b@example.com", phone="+200", channel="email"), "disk full")
    assert smtp.sent == ["b@example.com"]
    assert sms.sent == []


def _compares_channel_names(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {"sms", "email", "SMS", "EMAIL"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and side.value in names:
                    return True
                if isinstance(side, ast.Attribute) and side.attr in names:
                    return True
        if isinstance(node, ast.match_case) and "sms" in ast.unparse(node.pattern).lower():
            return True
    return False


def test_design_mail_notifier_knows_nothing_of_sms() -> None:
    assert "sms" not in Path("alerts/email.py").read_text(encoding="utf-8").lower()


def test_design_service_does_not_branch_on_the_channel_name() -> None:
    assert not _compares_channel_names(Path("alerts/service.py"))


def test_design_notifier_contract_is_an_abstract_base_class() -> None:
    for path in Path("alerts").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                assert "Protocol" not in {ast.unparse(base) for base in node.bases}, f"{node.name} is a Protocol"
