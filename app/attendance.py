import sqlite3
from datetime import datetime, date, time as dtime, timezone, timedelta

from app.db import db_session
from app.config import DEFAULT_TIMEZONE_HOURS, DEFAULT_TIMEZONE_MINUTES, PUNCH_DEBOUNCE_SECONDS

IST = timezone(timedelta(hours=DEFAULT_TIMEZONE_HOURS, minutes=DEFAULT_TIMEZONE_MINUTES))


def format_duration(hours: float) -> str:
    """Format decimal hours into human readable 'Xh Ym' or 'Z mins'."""
    if hours <= 0:
        return "0 mins"
    total_minutes = int(round(hours * 60))
    if total_minutes < 60:
        return f"{total_minutes} mins"
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h}h {m}m" if m > 0 else f"{h} hrs"


def record_staff_punch(staff_id: str, now: datetime | None = None) -> dict:
    """Process a live face scan for a hotel staff member.

    Maintains First IN (morning start) and Last OUT (evening departure) shift tracking.
    Intermediate passes automatically update the last out timestamp and recalculate total
    active hours worked today, with a debounce check to prevent multi-frame spam.
    """
    now = now.astimezone(IST) if now else datetime.now(IST)
    work_date = now.date().isoformat()
    punch_time_str = now.strftime('%Y-%m-%d %H:%M:%S')
    time_display = now.strftime('%I:%M %p')

    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, first_in, last_out, total_hours, punch_count, last_punch_at, status
            FROM daily_attendance
            WHERE staff_id = ? AND work_date = ?
            """,
            (staff_id, work_date),
        ).fetchone()

        if row is None:
            # First punch of the day: Clock In
            conn.execute(
                """
                INSERT INTO daily_attendance
                (staff_id, work_date, first_in, last_out, total_hours, punch_count, last_punch_at, status)
                VALUES (?, ?, ?, ?, 0.0, 1, ?, 'Working')
                """,
                (staff_id, work_date, punch_time_str, punch_time_str, punch_time_str),
            )
            conn.execute(
                """
                INSERT INTO attendance_punches (staff_id, punch_time, work_date)
                VALUES (?, ?, ?)
                """,
                (staff_id, punch_time_str, work_date),
            )

            # Backward-compatibility for legacy attendance table
            session_name = "morning" if now.hour < 12 else "afternoon"
            try:
                conn.execute(
                    "INSERT INTO attendance (student_id, session_date, session) VALUES (?, ?, ?)",
                    (staff_id, work_date, session_name),
                )
            except sqlite3.IntegrityError:
                pass

            return {
                "action": "IN",
                "status": "clock_in",
                "work_date": work_date,
                "first_in": time_display,
                "last_out": time_display,
                "total_hours": 0.0,
                "duration_str": "Just clocked in",
                "message": f"Shift started at {time_display}",
                "speech": f"Welcome, clocked in at {time_display}",
                "already": False,
                "session": session_name,
            }

        # Subsequent punch of the day
        try:
            last_punch_dt = datetime.strptime(row["last_punch_at"], '%Y-%m-%d %H:%M:%S').replace(tzinfo=IST)
            secs_since_last = (now - last_punch_dt).total_seconds()
        except Exception:
            secs_since_last = 999.0

        try:
            first_in_dt = datetime.strptime(row["first_in"], '%Y-%m-%d %H:%M:%S').replace(tzinfo=IST)
            first_in_display = first_in_dt.strftime('%I:%M %p')
        except Exception:
            first_in_display = row["first_in"]
            first_in_dt = now

        # Debounce: if scanned within debounce seconds, avoid duplicate punch logging
        if secs_since_last < PUNCH_DEBOUNCE_SECONDS:
            total_hours = float(row["total_hours"])
            return {
                "action": "DEBOUNCE",
                "status": "active",
                "work_date": work_date,
                "first_in": first_in_display,
                "last_out": now.strftime('%I:%M %p'),
                "total_hours": total_hours,
                "duration_str": format_duration(total_hours),
                "message": f"Active shift: {format_duration(total_hours)} (In: {first_in_display})",
                "speech": None,
                "already": True,
                "session": "present",
            }

        # Update Last OUT and recompute total hours worked
        elapsed_seconds = max(0.0, (now - first_in_dt).total_seconds())
        total_hours = round(elapsed_seconds / 3600.0, 2)
        duration_str = format_duration(total_hours)
        status_label = "Completed" if total_hours >= 4.0 else "Working"

        conn.execute(
            """
            UPDATE daily_attendance
            SET last_out = ?, total_hours = ?, punch_count = punch_count + 1, last_punch_at = ?, status = ?
            WHERE id = ?
            """,
            (punch_time_str, total_hours, punch_time_str, status_label, row["id"]),
        )
        conn.execute(
            """
            INSERT INTO attendance_punches (staff_id, punch_time, work_date)
            VALUES (?, ?, ?)
            """,
            (staff_id, punch_time_str, work_date),
        )

        return {
            "action": "UPDATE",
            "status": "clock_update",
            "work_date": work_date,
            "first_in": first_in_display,
            "last_out": time_display,
            "total_hours": total_hours,
            "duration_str": duration_str,
            "message": f"Shift updated: {duration_str} (First In: {first_in_display} → Out: {time_display})",
            "speech": f"Shift updated, {duration_str} logged",
            "already": True,
            "session": "present",
        }


def mark_attendance(student_id: str, now: datetime | None = None) -> dict:
    """Legacy alias used by scanner."""
    return record_staff_punch(student_id, now)
