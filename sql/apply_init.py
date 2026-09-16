import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from lib.db import _connect_kwargs, get_connection  # noqa: E402
import snowflake.connector  # noqa: E402


def main() -> None:
    kwargs = _connect_kwargs()
    kwargs.pop("database", None)
    kwargs.pop("schema", None)
    print("Connecting with key-pair (no password / Duo)...")
    conn = snowflake.connector.connect(**kwargs)
    cur = conn.cursor()
    sql = (BACKEND / "sql" / "init.sql").read_text(encoding="utf-8")
    cleaned = re.sub(r"(?m)^\s*--.*$", "", sql)
    statements = [part.strip() for part in cleaned.split(";") if part.strip()]
    for index, statement in enumerate(statements, 1):
        preview = " ".join(statement.split())[:90]
        print(f"[{index}/{len(statements)}] {preview}")
        cur.execute(statement)

    print("Verifying...")
    cur.execute("SHOW TABLES IN SCHEMA TRANSIT_SURVEY.STARTUP_FORM")
    tables = [row[1] for row in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM TRANSIT_SURVEY.STARTUP_FORM.LANGUAGES")
    language_count = cur.fetchone()[0]
    cur.close()
    conn.close()
    print("Tables:", ", ".join(tables))
    print("Seeded languages:", language_count)
    print("Done.")


if __name__ == "__main__":
    main()
