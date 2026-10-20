import json

from reports.export import export
from reports.model import Report, Row


def test_json() -> None:
    report = Report(period="2026-10", rows=(Row(product="tea", units=3, revenue=12.0),))
    assert json.loads(export(report))["period"] == "2026-10"
