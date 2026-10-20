"""Reports in the forms the export page offers."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict

from reports.model import Report


def export(report: Report) -> str:
    """`report` as a JSON document."""
    return json.dumps(asdict(report))


def export_csv(report: Report) -> str:
    """`report` as CSV, one line per product under a header."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["product", "units", "revenue"])
    writer.writerows([row.product, row.units, row.revenue] for row in report.rows)
    return buffer.getvalue()
