import gzip
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def back_up_database(db_name: str, output_dir: Path) -> Path:
    target = output_dir / f"{db_name}-{datetime.now(UTC):%Y%m%d}.sql.gz"
    dump = subprocess.run(["pg_dump", "--", db_name], capture_output=True, check=True, timeout=600)
    with gzip.open(target, "wb") as archive:
        archive.write(dump.stdout)
    return target
