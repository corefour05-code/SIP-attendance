import re

from app.db import db_session

ID_PATTERN = re.compile(r"^IT(\d{3})$")
MOBILE_PATTERN = re.compile(r"^\d{10}$")


def normalize_mobile(raw: str) -> str | None:
    """Strip formatting and an optional +91/91 country code; returns None if
    what's left isn't a plain 10-digit number."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if MOBILE_PATTERN.match(digits) else None


def next_student_id(conn=None) -> str:
    def _compute(c):
        rows = c.execute("SELECT student_id FROM students").fetchall()
        max_num = 0
        for row in rows:
            m = ID_PATTERN.match(row["student_id"])
            if m:
                max_num = max(max_num, int(m.group(1)))
        return f"IT{max_num + 1:03d}"

    if conn is not None:
        return _compute(conn)
    with db_session() as c:
        return _compute(c)


def student_exists(conn, student_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM students WHERE student_id = ?", (student_id,)
    ).fetchone()
    return row is not None


def list_students(conn):
    return conn.execute(
        """
        SELECT s.student_id, s.name, s.mobile_number, s.created_at, COUNT(e.id) AS photo_count
        FROM students s
        LEFT JOIN embeddings e ON e.student_id = s.student_id
        GROUP BY s.student_id
        ORDER BY s.student_id
        """
    ).fetchall()


def get_student(conn, student_id: str):
    return conn.execute(
        "SELECT student_id, name, mobile_number, created_at FROM students WHERE student_id = ?", (student_id,)
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
    """Used by the CSV roster import — a real students row with no face
    photos yet, completed later on enrollment day by mobile-number lookup."""
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
            (student_id, embedding_to_blob(photo["embedding"]), photo["angle_label"]),
        )
