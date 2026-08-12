from __future__ import annotations

from pathlib import Path

from backend.config import get_settings
from backend.persistence.database import connection


def migrate() -> None:
    migrations = sorted(Path(__file__).with_name("migrations").glob("*.sql"))
    with connection(get_settings()) as conn:
        with conn.cursor() as cur:
            # Bootstrap the tracker safely; 001 itself may pre-date it.
            cur.execute("CREATE TABLE IF NOT EXISTS deallens_schema_migrations (version TEXT PRIMARY KEY, name TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
            cur.execute("SELECT version FROM deallens_schema_migrations")
            applied = {row["version"] for row in cur.fetchall()}
            for path in migrations:
                version = path.name.split("_", 1)[0]
                if version in applied:
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO deallens_schema_migrations (version, name) VALUES (%s, %s)", (version, path.name))


if __name__ == "__main__":
    migrate()
