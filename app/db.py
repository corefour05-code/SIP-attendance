import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "sip.db")))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
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
    """Idempotent ALTERs and table creations for upgrades."""
    # Ensure students columns
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(students)")}
    if "mobile_number" not in cols:
        conn.execute("ALTER TABLE students ADD COLUMN mobile_number TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_students_mobile ON students(mobile_number)"
        )

    # Ensure daily_attendance exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_attendance (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id       TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
            work_date      DATE NOT NULL,
            first_in       TEXT NOT NULL,
            last_out       TEXT NOT NULL,
            total_hours    REAL NOT NULL DEFAULT 0.0,
            punch_count    INTEGER NOT NULL DEFAULT 1,
            last_punch_at  TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'Working',
            UNIQUE (staff_id, work_date)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_att_date ON daily_attendance(work_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_att_staff ON daily_attendance(staff_id)")

    # Ensure attendance_punches exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_punches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id    TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
            punch_time  TEXT NOT NULL,
            work_date   DATE NOT NULL,
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_punches_date ON attendance_punches(work_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_punches_staff ON attendance_punches(staff_id)")

    # Migrate any legacy attendance records if daily_attendance is empty
    legacy_count = conn.execute("SELECT COUNT(*) AS c FROM attendance").fetchone()["c"]
    daily_count = conn.execute("SELECT COUNT(*) AS c FROM daily_attendance").fetchone()["c"]
    if legacy_count > 0 and daily_count == 0:
        legacy_rows = conn.execute(
            "SELECT student_id, session_date, marked_at FROM attendance ORDER BY marked_at"
        ).fetchall()
        for r in legacy_rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO daily_attendance
                (staff_id, work_date, first_in, last_out, total_hours, punch_count, last_punch_at, status)
                VALUES (?, ?, ?, ?, 0.0, 1, ?, 'Present')
                """,
                (r["student_id"], r["session_date"], r["marked_at"], r["marked_at"], r["marked_at"]),
            )

    conn.commit()


def init_schema():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        _migrate(conn)
    finally:
        conn.close()
