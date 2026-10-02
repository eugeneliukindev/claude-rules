import os


def back_up_database(db_name: str, output_dir: str) -> None:
    if os.system("pg_dump " + db_name + " | gzip > " + output_dir + "/dump.sql.gz") != 0:
        raise RuntimeError(db_name)
