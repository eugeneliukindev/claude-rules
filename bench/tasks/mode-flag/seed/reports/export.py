"""Reports in the forms the export page offers."""

from __future__ import annotations

import json
from dataclasses import asdict

from reports.model import Report


def export(report: Report) -> str:
    """`report` as a JSON document."""
    return json.dumps(asdict(report))
