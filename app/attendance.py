import sqlite3
from datetime import datetime, date, time as dtime

from app.db import db_session

NOON = dtime(12, 0)


def current_session(now: datetime | None = None) -> tuple[date, str]:
    now = now or datetime.now()
    session = "morning" if now.time() < NOON else "afternoon"
    return now.date(), session


def mark_attendance(student_id: str, now: datetime | None = None) -> dict:
    session_date, session = current_session(now)
    with db_session() as conn:
        try:
            conn.execute(
                "INSERT INTO attendance (student_id, session_date, session) VALUES (?, ?, ?)",
                (student_id, session_date.isoformat(), session),
            )
            already = False
        except sqlite3.IntegrityError:
            already = True

    return {
        "already": already,
        "session": session,
        "session_date": session_date.isoformat(),
    }
