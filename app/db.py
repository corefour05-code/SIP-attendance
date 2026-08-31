import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "sip.db")))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection):
    """Idempotent ALTERs for columns added after the initial schema — plain
    CREATE TABLE IF NOT EXISTS in schema.sql doesn't retrofit existing DBs."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(students)")}
    if "mobile_number" not in cols:
        conn.execute("ALTER TABLE students ADD COLUMN mobile_number TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_students_mobile ON students(mobile_number)"
        )
    conn.commit()


def init_schema():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
        _migrate(conn)
    finally:
        conn.close()
