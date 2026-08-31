"""Import the pre-event roster CSV (Google Form export: Timestamp, Name,
Phone number, Gender, Date of Birth) into the students table as
not-yet-face-captured rows, keyed by mobile number.

Safe to re-run whenever a new batch of the roster arrives — phone numbers
already in the DB are skipped, so it only ever adds new students.

Usage:
    venv\\Scripts\\python.exe import_students.py "PSNA SIP 2026-2030.csv"
"""

import csv
import re
import sys
from datetime import datetime

from app.db import db_session, init_schema
from app.students import next_student_id, mobile_in_use, create_preregistered_student, normalize_mobile

NAME_COL = "Name (Initial At Last)"
PHONE_COL = "Phone number"
TIMESTAMP_COL = "Timestamp"
TIMESTAMP_FMT = "%Y/%m/%d %I:%M:%S %p GMT+5:30"


def clean_phone(raw: str) -> str | None:
    p = raw.strip()
    if "," in p:
        p = p.split(",", 1)[0].strip()  # multiple numbers typed into one field — take the first
    return normalize_mobile(p)


def clean_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip())


def load_rows(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def dedupe_by_phone(rows: list[dict]) -> dict[str, dict]:
    """Same phone number submitted more than once (typo corrections) —
    keep the latest timestamp per phone."""
    best: dict[str, dict] = {}
    for row in rows:
        phone = clean_phone(row[PHONE_COL])
        if phone is None:
            continue
        ts = datetime.strptime(row[TIMESTAMP_COL].strip(), TIMESTAMP_FMT)
        if phone not in best or ts > best[phone]["_ts"]:
            best[phone] = {"name": clean_name(row[NAME_COL]), "phone": phone, "_ts": ts}
    return best


def main():
    if len(sys.argv) != 2:
        print("Usage: python import_students.py <csv_path>")
        sys.exit(1)

    csv_path = sys.argv[1]
    init_schema()

    rows = load_rows(csv_path)
    invalid = [r for r in rows if clean_phone(r[PHONE_COL]) is None]
    deduped = dedupe_by_phone(rows)

    inserted, skipped_existing = [], []
    with db_session() as conn:
        for phone, info in sorted(deduped.items(), key=lambda kv: kv[1]["_ts"]):
            if mobile_in_use(conn, phone):
                skipped_existing.append((phone, info["name"]))
                continue
            student_id = next_student_id(conn)
            create_preregistered_student(conn, student_id, info["name"], phone)
            inserted.append((student_id, phone, info["name"]))

    print(f"Read {len(rows)} rows from {csv_path}")
    print(f"Invalid/unparseable phone numbers ({len(invalid)}):")
    for r in invalid:
        print(f"  {r[NAME_COL]!r}: {r[PHONE_COL]!r}")
    print(f"Already in DB, skipped ({len(skipped_existing)}):")
    for phone, name in skipped_existing:
        print(f"  {phone} — {name}")
    print(f"Inserted ({len(inserted)}):")
    for student_id, phone, name in inserted:
        print(f"  {student_id}  {phone}  {name}")


if __name__ == "__main__":
    main()
