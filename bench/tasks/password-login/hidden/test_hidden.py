"""Hidden checks for password-login: passwords work, and hashing sits behind a contract."""

import ast
import importlib
import inspect
from pathlib import Path

from accounts.app import build_service


def test_gate_right_password_logs_in() -> None:
    service = build_service()
    service.register("a@example.com", "s3cret")
    assert service.log_in("a@example.com", "s3cret") is True


def test_gate_wrong_password_or_email_fails() -> None:
    service = build_service()
    service.register("a@example.com", "s3cret")
    assert service.log_in("a@example.com", "guess") is False
    assert service.log_in("b@example.com", "s3cret") is False


def _imported_modules(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_design_service_does_not_hash_itself() -> None:
    found = _imported_modules(Path("accounts/service.py")) & {"hashlib", "secrets", "os", "hmac"}
    assert not found, f"accounts/service.py uses the mechanism directly: {sorted(found)}"


def test_design_hashing_has_an_abstract_contract() -> None:
    contracts = set()
    for path in Path("accounts").rglob("*.py"):
        module = importlib.import_module(".".join(path.with_suffix("").parts).removesuffix(".__init__"))
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__.startswith("accounts") and inspect.isabstract(cls) and cls.__name__ != "UserStore":
                contracts.add(cls.__name__)
    assert contracts, "no abstract contract besides UserStore"
