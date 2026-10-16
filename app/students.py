import re
from app.db import db_session

# Matches HTL001, EMP001, IT001, etc.
ID_PATTERN = re.compile(r"^([A-Za-z]+)(\d+)$")
MOBILE_PATTERN = re.compile(r"^\d{10}$")


def normalize_mobile(raw: str) -> str | None:
    """Strip formatting and an optional +91/91 country code; returns None if
    what's left isn't a plain 10-digit number."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if MOBILE_PATTERN.match(digits) else None


def next_staff_id(conn=None, prefix: str = "HTL") -> str:
    """Generate next staff ID, e.g. HTL001, HTL002..."""
    def _compute(c):
        rows = c.execute("SELECT student_id FROM students").fetchall()
        max_num = 0
        for row in rows:
            m = ID_PATTERN.match(row["student_id"])
            if m:
                try:
                    max_num = max(max_num, int(m.group(2)))
                except ValueError:
                    pass
        return f"{prefix}{max_num + 1:03d}"

    if conn is not None:
        return _compute(conn)
    with db_session() as c:
        return _compute(c)


def next_student_id(conn=None) -> str:
    """Alias for backwards compatibility."""
    return next_staff_id(conn, prefix="HTL")


def student_exists(conn, student_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM students WHERE student_id = ?", (student_id,)
    ).fetchone()
    return row is not None


def list_students(conn):
    """List all hotel staff with photo counts and today's shift status."""
    return conn.execute(
        """
        SELECT 
            s.student_id, 
            s.name, 
            s.mobile_number, 
            s.created_at, 
            COUNT(e.id) AS photo_count,
            da.first_in,
            da.last_out,
            da.total_hours,
            da.status AS today_status
        FROM students s
        LEFT JOIN embeddings e ON e.student_id = s.student_id
        LEFT JOIN daily_attendance da ON da.staff_id = s.student_id AND da.work_date = DATE('now', '+5 hours', '30 minutes')
        GROUP BY s.student_id
        ORDER BY s.student_id
        """
    ).fetchall()


def get_student(conn, student_id: str):
    return conn.execute(
        """
        SELECT student_id, name, mobile_number, created_at
        FROM students
        WHERE student_id = ?
        """,
        (student_id,),
    ).fetchone()


def find_by_mobile(conn, mobile_number: str):
    row = conn.execute(
        "SELECT student_id, name, mobile_number FROM students WHERE mobile_number = ?",
        (mobile_number,),
    ).fetchone()
    if row is None:
        return None
    photo_count = conn.execute(
        "SELECT COUNT(*) AS c FROM embeddings WHERE student_id = ?", (row["student_id"],)
    ).fetchone()["c"]
    return {
        "student_id": row["student_id"],
        "name": row["name"],
        "mobile_number": row["mobile_number"],
        "photo_count": photo_count,
    }


def mobile_in_use(conn, mobile_number: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM students WHERE mobile_number = ?", (mobile_number,)
    ).fetchone()
    return row is not None


def update_student_name(conn, student_id: str, name: str):
    conn.execute("UPDATE students SET name = ? WHERE student_id = ?", (name, student_id))


def update_student_mobile(conn, student_id: str, mobile_number: str | None):
    conn.execute("UPDATE students SET mobile_number = ? WHERE student_id = ?", (mobile_number, student_id))


def create_preregistered_student(conn, student_id: str, name: str, mobile_number: str):
    conn.execute(
        "INSERT INTO students (student_id, name, mobile_number) VALUES (?, ?, ?)",
        (student_id, name, mobile_number),
    )


def delete_student(conn, student_id: str):
    conn.execute("DELETE FROM students WHERE student_id = ?", (student_id,))


def replace_embeddings(conn, student_id: str, photos: list[dict]):
    from app.face import embedding_to_blob

    conn.execute("DELETE FROM embeddings WHERE student_id = ?", (student_id,))
    for photo in photos:
        conn.execute(
            "INSERT INTO embeddings (student_id, embedding, angle_label) VALUES (?, ?, ?)",
            (student_id, embedding_to_blob(photo["embedding"]), photo.get("angle_label", "original")),
        )
