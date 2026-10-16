PRAGMA journal_mode = WAL;

-- Hotel Staff Directory
CREATE TABLE IF NOT EXISTS students (
    student_id     TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    mobile_number  TEXT UNIQUE,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Biometric Face Embeddings
CREATE TABLE IF NOT EXISTS embeddings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    embedding   BLOB NOT NULL,
    angle_label TEXT NOT NULL DEFAULT 'original',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_embeddings_student_id ON embeddings(student_id);

-- Daily Attendance & Work Shift Hours (Morning First IN & Evening Last OUT)
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
);

CREATE INDEX IF NOT EXISTS idx_daily_att_date ON daily_attendance(work_date);
CREATE INDEX IF NOT EXISTS idx_daily_att_staff ON daily_attendance(staff_id);

-- Individual Punch Audit Log (Every time a staff passes/scans at the terminal)
CREATE TABLE IF NOT EXISTS attendance_punches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id    TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    punch_time  TEXT NOT NULL,
    work_date   DATE NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_punches_date ON attendance_punches(work_date);
CREATE INDEX IF NOT EXISTS idx_punches_staff ON attendance_punches(staff_id);

-- Legacy attendance table (retained for backward compatibility)
CREATE TABLE IF NOT EXISTS attendance (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    session_date DATE NOT NULL,
    session      TEXT NOT NULL,
    marked_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, session_date, session)
);

CREATE TABLE IF NOT EXISTS coordinator (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    username      TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL
);
