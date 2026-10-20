"""Reports in the forms the export page offers."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict

from reports.model import Report


def export(report: Report, format: str = "json") -> str:  # noqa: A002
    """`report` as JSON or CSV."""
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["product", "units", "revenue"])
        writer.writerows([row.product, row.units, row.revenue] for row in report.rows)
        return buffer.getvalue()
    return json.dumps(asdict(report))
