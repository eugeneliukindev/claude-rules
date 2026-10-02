import subprocess
from pathlib import Path


def back_up_database(db_name: str, output_dir: Path) -> Path:
    target = output_dir / f"{db_name}.sql.gz"
    subprocess.run(f"pg_dump {db_name} | gzip > {target}", shell=True, check=True)
    return target
