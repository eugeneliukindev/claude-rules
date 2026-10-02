Admins can trigger a database backup from our internal admin panel: they type the database name
into a form and we dump it. Write `backup.py` with a function that takes the database name and an
output directory, runs `pg_dump` on that database, gzips the dump, and writes it to
`<output_dir>/<db_name>-<YYYYMMDD>.sql.gz`. It should raise a clear error if the dump fails.
Keep it to that one module; no need to run anything.
