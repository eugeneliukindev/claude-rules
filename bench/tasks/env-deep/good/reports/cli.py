"""`reports ID`: print a report from the reports service."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from reports.client import Opener, fetch_report, open_url

SERVICE_URL = "https://reports.example.com"


def main(argv: Sequence[str] | None = None, *, opener: Opener = open_url) -> None:
    """Print the report the command line names; `REPORTS_URL` overrides the service URL."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_id", type=int)
    arguments = parser.parse_args(argv)
    base_url = os.environ.get("REPORTS_URL", SERVICE_URL)
    print(json.dumps(fetch_report(arguments.report_id, base_url=base_url, opener=opener)))
