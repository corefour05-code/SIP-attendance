PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS students (
    student_id     TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    mobile_number  TEXT UNIQUE,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embeddings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    embedding   BLOB NOT NULL,
    angle_label TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_embeddings_student_id ON embeddings(student_id);

CREATE TABLE IF NOT EXISTS attendance (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    session_date DATE NOT NULL,
    session      TEXT NOT NULL CHECK (session IN ('morning', 'afternoon')),
    marked_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, session_date, session)
);

CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(session_date);

CREATE TABLE IF NOT EXISTS coordinator (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    username      TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL
);
