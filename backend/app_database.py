"""SQLite storage for accounts and analysis history."""

from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


DATABASE_PATH = Path(os.environ.get(
    "NTG_APP_DATABASE", Path(__file__).resolve().parent / "data" / "app.sqlite"
)).resolve()

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_user (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE COLLATE NOCASE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    password_hash TEXT,
    is_guest INTEGER NOT NULL CHECK (is_guest IN (0, 1)),
    created_at INTEGER NOT NULL,
    CHECK ((is_guest = 1 AND email IS NULL AND password_hash IS NULL)
        OR (is_guest = 0 AND email IS NOT NULL AND password_hash IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS session (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS session_user ON session(user_id);
CREATE TABLE IF NOT EXISTS password_reset (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS reset_user ON password_reset(user_id);
CREATE TABLE IF NOT EXISTS analysis (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload))
);
CREATE INDEX IF NOT EXISTS analysis_owner_date ON analysis(user_id, created_at DESC);
"""


@contextmanager
def connection():
    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        with con:
            yield con


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connection() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(SCHEMA)
        con.execute("DELETE FROM session WHERE expires_at <= ?", (int(time.time()),))
        con.execute("DELETE FROM password_reset WHERE expires_at <= ?", (int(time.time()),))


def public_user(row) -> dict:
    return {key: bool(row[key]) if key == "is_guest" else row[key]
            for key in ("id", "email", "first_name", "last_name", "is_guest")}


def create_user(email: str | None, first_name: str, last_name: str,
                password_hash: str | None, *, guest: bool = False) -> dict:
    user_id = str(uuid4())
    with connection() as con:
        con.execute("INSERT INTO app_user VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, email, first_name, last_name, password_hash, int(guest), int(time.time())))
        row = con.execute("SELECT * FROM app_user WHERE id = ?", (user_id,)).fetchone()
        return public_user(row)


def find_user(email: str) -> dict | None:
    with connection() as con:
        row = con.execute("SELECT * FROM app_user WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def create_session(token_hash: str, user_id: str, expires_at: int,
                   old_token_hash: str | None) -> None:
    with connection() as con:
        con.execute("DELETE FROM session WHERE token_hash = ? OR expires_at <= ?",
                    (old_token_hash, int(time.time())))
        con.execute("INSERT INTO session VALUES (?, ?, ?)", (token_hash, user_id, expires_at))


def get_session_user(token_hash: str) -> dict | None:
    with connection() as con:
        row = con.execute(
            """SELECT u.* FROM session s JOIN app_user u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (token_hash, int(time.time())),
        ).fetchone()
        return public_user(row) if row else None


def delete_session(token_hash: str) -> None:
    with connection() as con:
        con.execute("DELETE FROM session WHERE token_hash = ?", (token_hash,))


def create_reset(user_id: str, token_hash: str, expires_at: int) -> None:
    with connection() as con:
        con.execute("DELETE FROM password_reset WHERE user_id = ? OR expires_at <= ?",
                    (user_id, int(time.time())))
        con.execute("INSERT INTO password_reset VALUES (?, ?, ?)", (token_hash, user_id, expires_at))


def reset_password(token_hash: str, password_hash: str) -> bool:
    with connection() as con:
        # Prevent two requests from using the same reset link.
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT user_id FROM password_reset WHERE token_hash = ? AND expires_at > ?",
                          (token_hash, int(time.time()))).fetchone()
        if row is None:
            return False
        con.execute("UPDATE app_user SET password_hash = ? WHERE id = ?", (password_hash, row[0]))
        con.execute("DELETE FROM password_reset WHERE user_id = ?", (row[0],))
        con.execute("DELETE FROM session WHERE user_id = ?", (row[0],))
        return True


def save_analysis(user_id: str, payload: dict) -> dict:
    result = {**payload, "id": str(uuid4()), "created_at": int(time.time())}
    encoded = json.dumps(result, allow_nan=False)
    with connection() as con:
        con.execute("INSERT INTO analysis VALUES (?, ?, ?, ?)",
                    (result["id"], user_id, result["created_at"], encoded))
    return result


def get_analysis(user_id: str, analysis_id: str) -> dict | None:
    with connection() as con:
        row = con.execute("SELECT payload FROM analysis WHERE id = ? AND user_id = ?",
                          (analysis_id, user_id)).fetchone()
        return json.loads(row[0]) if row else None


def list_analyses(user_id: str, limit: int, offset: int) -> dict:
    with connection() as con:
        rows = con.execute(
            "SELECT payload FROM analysis WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
        total = con.execute("SELECT COUNT(*) FROM analysis WHERE user_id = ?", (user_id,)).fetchone()[0]
        return {"items": [json.loads(row[0]) for row in rows], "total": total,
                "limit": limit, "offset": offset}
