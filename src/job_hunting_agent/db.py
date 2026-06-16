from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DATA_DIR = Path(os.getenv("JOB_AGENT_DATA_DIR", "data"))
DATABASE_URL = os.getenv("JOB_AGENT_DATABASE_URL", f"sqlite:///{DATA_DIR / 'job_agent.db'}")
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


@contextmanager
def connection() -> Iterator[Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if IS_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            yield conn
            conn.commit()
    else:
        db_path = DATABASE_URL.replace("sqlite:///", "", 1)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()


def init_db() -> None:
    if IS_POSTGRES:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
              id SERIAL PRIMARY KEY,
              email VARCHAR(320) UNIQUE NOT NULL,
              created_at TIMESTAMPTZ NOT NULL,
              last_login_at TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS otp_codes (
              id SERIAL PRIMARY KEY,
              email VARCHAR(320) NOT NULL,
              code_hash VARCHAR(128) NOT NULL,
              expires_at TIMESTAMPTZ NOT NULL,
              consumed BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS run_records (
              id SERIAL PRIMARY KEY,
              user_email VARCHAR(320) NOT NULL,
              trigger VARCHAR(32) NOT NULL,
              ats_score INTEGER NOT NULL,
              job_count INTEGER NOT NULL,
              application_summary JSONB NOT NULL,
              output_dir TEXT NOT NULL,
              generated_at VARCHAR(64) NOT NULL,
              payload JSONB NOT NULL,
              created_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS application_records (
              id SERIAL PRIMARY KEY,
              run_id INTEGER NOT NULL,
              user_email VARCHAR(320) NOT NULL,
              portal VARCHAR(64) NOT NULL,
              title TEXT NOT NULL,
              company TEXT NOT NULL,
              status VARCHAR(64) NOT NULL,
              recruiter_email VARCHAR(320) NOT NULL DEFAULT '',
              job_url TEXT NOT NULL,
              detail TEXT NOT NULL,
              draft_path TEXT NOT NULL DEFAULT '',
              created_at TIMESTAMPTZ NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_otp_codes_email ON otp_codes(email)",
            "CREATE INDEX IF NOT EXISTS idx_run_records_user ON run_records(user_email)",
            "CREATE INDEX IF NOT EXISTS idx_application_records_user ON application_records(user_email)",
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL,
              last_login_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS otp_codes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT NOT NULL,
              code_hash TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              consumed INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS run_records (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_email TEXT NOT NULL,
              trigger TEXT NOT NULL,
              ats_score INTEGER NOT NULL,
              job_count INTEGER NOT NULL,
              application_summary TEXT NOT NULL,
              output_dir TEXT NOT NULL,
              generated_at TEXT NOT NULL,
              payload TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS application_records (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER NOT NULL,
              user_email TEXT NOT NULL,
              portal TEXT NOT NULL,
              title TEXT NOT NULL,
              company TEXT NOT NULL,
              status TEXT NOT NULL,
              recruiter_email TEXT NOT NULL DEFAULT '',
              job_url TEXT NOT NULL,
              detail TEXT NOT NULL,
              draft_path TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_otp_codes_email ON otp_codes(email)",
            "CREATE INDEX IF NOT EXISTS idx_run_records_user ON run_records(user_email)",
            "CREATE INDEX IF NOT EXISTS idx_application_records_user ON application_records(user_email)",
        ]
    with connection() as conn:
        for statement in statements:
            conn.execute(statement)


def ensure_user(email: str) -> None:
    normalized = normalize_email(email)
    now = _serialize_time(utcnow())
    with connection() as conn:
        row = _fetchone(conn, "SELECT id FROM users WHERE email = ?", (normalized,))
        if row:
            _execute(conn, "UPDATE users SET last_login_at = ? WHERE email = ?", (now, normalized))
            return
        _execute(conn, "INSERT INTO users (email, created_at, last_login_at) VALUES (?, ?, ?)", (normalized, now, now))


def save_otp(email: str, code_hash: str, expires_at: datetime) -> None:
    normalized = normalize_email(email)
    now = _serialize_time(utcnow())
    with connection() as conn:
        _execute(conn, "UPDATE otp_codes SET consumed = ? WHERE email = ? AND consumed = ?", (True, normalized, False))
        _execute(
            conn,
            "INSERT INTO otp_codes (email, code_hash, expires_at, consumed, created_at) VALUES (?, ?, ?, ?, ?)",
            (normalized, code_hash, _serialize_time(expires_at), False, now),
        )


def consume_valid_otp(email: str, code_hash: str) -> bool:
    normalized = normalize_email(email)
    with connection() as conn:
        row = _fetchone(
            conn,
            """
            SELECT id, expires_at FROM otp_codes
            WHERE email = ? AND code_hash = ? AND consumed = ?
            ORDER BY created_at DESC
            """,
            (normalized, code_hash, False),
        )
        if not row or _parse_time(row["expires_at"]) < utcnow():
            return False
        _execute(conn, "UPDATE otp_codes SET consumed = ? WHERE id = ?", (True, row["id"]))
    ensure_user(normalized)
    return True


def record_run(user_email: str, result: dict[str, Any]) -> int:
    normalized = normalize_email(user_email)
    now = _serialize_time(utcnow())
    summary = result.get("application_summary", {})
    with connection() as conn:
        cursor = _execute(
            conn,
            """
            INSERT INTO run_records
            (user_email, trigger, ats_score, job_count, application_summary, output_dir, generated_at, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized,
                result.get("trigger", "manual"),
                result.get("ats_report", {}).get("score", 0),
                len(result.get("jobs", [])),
                _json_dump(summary),
                result.get("output_dir", ""),
                result.get("generated_at", now),
                _json_dump(result),
                now,
            ),
        )
        run_id = _lastrowid(conn, cursor)
        for application in result.get("applications", []):
            job = application.get("job", {})
            _execute(
                conn,
                """
                INSERT INTO application_records
                (run_id, user_email, portal, title, company, status, recruiter_email, job_url, detail, draft_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    normalized,
                    job.get("portal", ""),
                    job.get("title", ""),
                    job.get("company", ""),
                    application.get("status", ""),
                    job.get("recruiter_email", ""),
                    job.get("url", ""),
                    application.get("detail", ""),
                    application.get("draft_path", ""),
                    now,
                ),
            )
    return int(run_id)


def latest_runs(user_email: str, limit: int = 10) -> list[dict[str, Any]]:
    normalized = normalize_email(user_email)
    with connection() as conn:
        rows = _fetchall(
            conn,
            """
            SELECT id, user_email, trigger, ats_score, job_count, application_summary, output_dir, generated_at, payload, created_at
            FROM run_records
            WHERE user_email = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (normalized, limit),
        )
    return [_decode_row(row) for row in rows]


def _execute(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return conn.execute(_sql(sql), _params(params))


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cursor = _execute(conn, sql, params)
    row = cursor.fetchone()
    return _row_to_dict(row) if row else None


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [_row_to_dict(row) for row in _execute(conn, sql, params).fetchall()]


def _sql(sql: str) -> str:
    return sql.replace("?", "%s") if IS_POSTGRES else sql


def _params(params: tuple[Any, ...]) -> tuple[Any, ...]:
    if IS_POSTGRES:
        return tuple(json.loads(value) if _looks_like_json(value) else value for value in params)
    return tuple(int(value) if isinstance(value, bool) else value for value in params)


def _lastrowid(conn: Any, cursor: Any) -> int:
    if IS_POSTGRES:
        return _fetchone(conn, "SELECT LASTVAL() AS id")["id"]
    return cursor.lastrowid


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("application_summary", "payload"):
        value = row.get(key)
        if isinstance(value, str):
            row[key] = json.loads(value)
    return row


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _looks_like_json(value: Any) -> bool:
    return isinstance(value, str) and value[:1] in {"{", "["}


def _serialize_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
