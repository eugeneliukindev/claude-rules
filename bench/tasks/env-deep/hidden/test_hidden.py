"""Hidden checks for env-deep: the variable works, and only the entry point reads it."""

import ast
import json
from pathlib import Path

import pytest


class Recording:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> bytes:
        self.urls.append(url)
        return json.dumps({"id": 7}).encode()


def test_gate_variable_sets_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from reports.cli import main

    monkeypatch.setenv("REPORTS_URL", "https://staging.example.com")
    opener = Recording()
    main(["7"], opener=opener)
    assert opener.urls == ["https://staging.example.com/reports/7"]


def test_gate_default_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from reports.cli import main

    monkeypatch.delenv("REPORTS_URL", raising=False)
    opener = Recording()
    main(["7"], opener=opener)
    assert opener.urls == ["https://reports.example.com/reports/7"]


def _reads_environment(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            return True
        if isinstance(node, ast.Name) and node.id in {"environ", "getenv"}:
            return True
    return False


def test_design_client_does_not_read_the_environment() -> None:
    assert not _reads_environment(Path("reports/client.py"))


def test_design_explicit_url_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    from reports.client import fetch_report

    monkeypatch.setenv("REPORTS_URL", "https://staging.example.com")
    opener = Recording()
    fetch_report(7, base_url="https://other.example.com", opener=opener)
    assert opener.urls == ["https://other.example.com/reports/7"]
