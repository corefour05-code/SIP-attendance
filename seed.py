"""One-time setup: create tables and the single coordinator login."""
import argparse
import getpass
import sys

from app.db import init_schema, db_session
from app.auth import hash_password


def main():
    parser = argparse.ArgumentParser(description="Seed the SIP attendance database")
    parser.add_argument("--username", default=None, help="Coordinator username (will prompt if omitted)")
    parser.add_argument("--password", default=None, help="Coordinator password (will prompt if omitted)")
    args = parser.parse_args()

    init_schema()

    username = args.username or input("Coordinator username: ").strip()
    password = args.password or getpass.getpass("Coordinator password: ")

    if not username or not password:
        print("Username and password are required.", file=sys.stderr)
        sys.exit(1)

    password_hash, salt = hash_password(password)

    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO coordinator (id, username, password_hash, salt)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                password_hash = excluded.password_hash,
                salt = excluded.salt
            """,
            (username, password_hash, salt),
        )

    print(f"Schema initialized and coordinator '{username}' set up.")


if __name__ == "__main__":
    main()
