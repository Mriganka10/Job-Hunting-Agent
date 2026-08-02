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
            CREATE TABLE IF NOT EXISTS email_verifications (
              id SERIAL PRIMARY KEY,
              email VARCHAR(320) UNIQUE NOT NULL,
              status VARCHAR(32) NOT NULL,
              provider VARCHAR(32) NOT NULL DEFAULT 'ses',
              requested_at TIMESTAMPTZ NOT NULL,
              verified_at TIMESTAMPTZ,
              last_checked_at TIMESTAMPTZ,
              detail TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
              id SERIAL PRIMARY KEY,
              user_email VARCHAR(320) UNIQUE NOT NULL,
              profile_payload JSONB NOT NULL,
              resume_path TEXT NOT NULL DEFAULT '',
              resume_uri TEXT NOT NULL DEFAULT '',
              resume_name TEXT NOT NULL DEFAULT '',
              created_at TIMESTAMPTZ NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL
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
            """
            CREATE TABLE IF NOT EXISTS scheduler_records (
              id SERIAL PRIMARY KEY,
              user_email VARCHAR(320) UNIQUE NOT NULL,
              active BOOLEAN NOT NULL DEFAULT TRUE,
              daily_at VARCHAR(5) NOT NULL,
              timezone VARCHAR(80) NOT NULL DEFAULT 'UTC',
              resume_path TEXT NOT NULL,
              resume_uri TEXT NOT NULL DEFAULT '',
              config_payload JSONB NOT NULL,
              next_run_at VARCHAR(64),
              last_run_at VARCHAR(64),
              last_error TEXT,
              last_result JSONB,
              created_at TIMESTAMPTZ NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_otp_codes_email ON otp_codes(email)",
            "CREATE INDEX IF NOT EXISTS idx_run_records_user ON run_records(user_email)",
            "CREATE INDEX IF NOT EXISTS idx_application_records_user ON application_records(user_email)",
            "CREATE INDEX IF NOT EXISTS idx_scheduler_records_active ON scheduler_records(active)",
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
            CREATE TABLE IF NOT EXISTS email_verifications (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              status TEXT NOT NULL,
              provider TEXT NOT NULL DEFAULT 'ses',
              requested_at TEXT NOT NULL,
              verified_at TEXT,
              last_checked_at TEXT,
              detail TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_email TEXT UNIQUE NOT NULL,
              profile_payload TEXT NOT NULL,
              resume_path TEXT NOT NULL DEFAULT '',
              resume_uri TEXT NOT NULL DEFAULT '',
              resume_name TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
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
            """
            CREATE TABLE IF NOT EXISTS scheduler_records (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_email TEXT UNIQUE NOT NULL,
              active INTEGER NOT NULL DEFAULT 1,
              daily_at TEXT NOT NULL,
              timezone TEXT NOT NULL DEFAULT 'UTC',
              resume_path TEXT NOT NULL,
              resume_uri TEXT NOT NULL DEFAULT '',
              config_payload TEXT NOT NULL,
              next_run_at TEXT,
              last_run_at TEXT,
              last_error TEXT,
              last_result TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_otp_codes_email ON otp_codes(email)",
            "CREATE INDEX IF NOT EXISTS idx_run_records_user ON run_records(user_email)",
            "CREATE INDEX IF NOT EXISTS idx_application_records_user ON application_records(user_email)",
            "CREATE INDEX IF NOT EXISTS idx_scheduler_records_active ON scheduler_records(active)",
        ]
    with connection() as conn:
        for statement in statements:
            conn.execute(statement)
        _ensure_column(conn, "scheduler_records", "timezone", "TEXT NOT NULL DEFAULT 'UTC'")
        _ensure_column(conn, "scheduler_records", "resume_uri", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "scheduler_records", "next_run_at", "TEXT")
        _ensure_column(conn, "scheduler_records", "last_run_at", "TEXT")
        _ensure_column(conn, "scheduler_records", "last_error", "TEXT")
        _ensure_column(conn, "scheduler_records", "last_result", "TEXT")
        _ensure_column(conn, "email_verifications", "provider", "TEXT NOT NULL DEFAULT 'ses'")
        _ensure_column(conn, "email_verifications", "verified_at", "TEXT")
        _ensure_column(conn, "email_verifications", "last_checked_at", "TEXT")
        _ensure_column(conn, "email_verifications", "detail", "TEXT NOT NULL DEFAULT ''")


def save_user_profile(
    user_email: str,
    profile_payload: dict[str, Any],
    *,
    resume_path: str = "",
    resume_uri: str = "",
    resume_name: str = "",
) -> None:
    normalized = normalize_email(user_email)
    now = _serialize_time(utcnow())
    payload = _json_dump(profile_payload)
    with connection() as conn:
        row = _fetchone(conn, "SELECT id FROM user_profiles WHERE user_email = ?", (normalized,))
        if row:
            _execute(
                conn,
                """
                UPDATE user_profiles
                SET profile_payload = ?,
                    resume_path = CASE WHEN ? = '' THEN resume_path ELSE ? END,
                    resume_uri = CASE WHEN ? = '' THEN resume_uri ELSE ? END,
                    resume_name = CASE WHEN ? = '' THEN resume_name ELSE ? END,
                    updated_at = ?
                WHERE user_email = ?
                """,
                (
                    payload,
                    resume_path,
                    resume_path,
                    resume_uri,
                    resume_uri,
                    resume_name,
                    resume_name,
                    now,
                    normalized,
                ),
            )
            return
        _execute(
            conn,
            """
            INSERT INTO user_profiles
            (user_email, profile_payload, resume_path, resume_uri, resume_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (normalized, payload, resume_path, resume_uri, resume_name, now, now),
        )


def user_profile(user_email: str) -> dict[str, Any] | None:
    normalized = normalize_email(user_email)
    with connection() as conn:
        row = _fetchone(
            conn,
            """
            SELECT user_email, profile_payload, resume_path, resume_uri, resume_name, created_at, updated_at
            FROM user_profiles
            WHERE user_email = ?
            """,
            (normalized,),
        )
    if not row:
        return None
    if isinstance(row.get("profile_payload"), str):
        row["profile_payload"] = json.loads(row["profile_payload"])
    return row


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


def save_email_verification(email: str, status: str, *, detail: str = "", provider: str = "ses") -> None:
    normalized = normalize_email(email)
    now = _serialize_time(utcnow())
    verified_at = now if status.lower() in {"success", "verified"} else None
    with connection() as conn:
        row = _fetchone(conn, "SELECT id FROM email_verifications WHERE email = ?", (normalized,))
        if row:
            if verified_at:
                _execute(
                    conn,
                    """
                    UPDATE email_verifications
                    SET status = ?, provider = ?, last_checked_at = ?,
                        verified_at = ?, detail = ?
                    WHERE email = ?
                    """,
                    (status, provider, now, verified_at, detail, normalized),
                )
            else:
                _execute(
                    conn,
                    """
                    UPDATE email_verifications
                    SET status = ?, provider = ?, last_checked_at = ?, detail = ?
                    WHERE email = ?
                    """,
                    (status, provider, now, detail, normalized),
                )
            return
        _execute(
            conn,
            """
            INSERT INTO email_verifications
            (email, status, provider, requested_at, verified_at, last_checked_at, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (normalized, status, provider, now, verified_at, now, detail),
        )


def email_verification(email: str) -> dict[str, Any] | None:
    normalized = normalize_email(email)
    with connection() as conn:
        return _fetchone(
            conn,
            """
            SELECT email, status, provider, requested_at, verified_at, last_checked_at, detail
            FROM email_verifications
            WHERE email = ?
            """,
            (normalized,),
        )


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


def save_schedule(
    user_email: str,
    *,
    daily_at: str,
    timezone_name: str,
    resume_path: str,
    resume_uri: str,
    config_payload: dict[str, Any],
    next_run_at: str,
) -> None:
    normalized = normalize_email(user_email)
    now = _serialize_time(utcnow())
    payload = _json_dump(config_payload)
    with connection() as conn:
        row = _fetchone(conn, "SELECT id FROM scheduler_records WHERE user_email = ?", (normalized,))
        if row:
            _execute(
                conn,
                """
                UPDATE scheduler_records
                SET active = ?, daily_at = ?, timezone = ?, resume_path = ?, resume_uri = ?,
                    config_payload = ?, next_run_at = ?, last_error = ?, updated_at = ?
                WHERE user_email = ?
                """,
                (True, daily_at, timezone_name, resume_path, resume_uri, payload, next_run_at, None, now, normalized),
            )
            return
        _execute(
            conn,
            """
            INSERT INTO scheduler_records
            (user_email, active, daily_at, timezone, resume_path, resume_uri, config_payload,
             next_run_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (normalized, True, daily_at, timezone_name, resume_path, resume_uri, payload, next_run_at, now, now),
        )


def disable_schedule(user_email: str) -> None:
    normalized = normalize_email(user_email)
    now = _serialize_time(utcnow())
    with connection() as conn:
        _execute(conn, "UPDATE scheduler_records SET active = ?, updated_at = ? WHERE user_email = ?", (False, now, normalized))


def update_schedule_status(
    user_email: str,
    *,
    next_run_at: str | None = None,
    last_run_at: str | None = None,
    last_error: str | None = None,
    last_result: dict[str, Any] | None = None,
) -> None:
    normalized = normalize_email(user_email)
    now = _serialize_time(utcnow())
    assignments = ["updated_at = ?"]
    params: list[Any] = [now]
    if next_run_at is not None:
        assignments.append("next_run_at = ?")
        params.append(next_run_at)
    if last_run_at is not None:
        assignments.append("last_run_at = ?")
        params.append(last_run_at)
    if last_error is not None:
        assignments.append("last_error = ?")
        params.append(last_error)
    if last_result is not None:
        assignments.append("last_result = ?")
        params.append(_json_dump(last_result))
    params.append(normalized)
    with connection() as conn:
        _execute(conn, f"UPDATE scheduler_records SET {', '.join(assignments)} WHERE user_email = ?", tuple(params))


def active_schedules(limit: int = 10) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = _fetchall(
            conn,
            """
            SELECT user_email, active, daily_at, timezone, resume_path, resume_uri, config_payload,
                   next_run_at, last_run_at, last_error, last_result, created_at, updated_at
            FROM scheduler_records
            WHERE active = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (True, limit),
        )
    return [_decode_schedule(row) for row in rows]


def schedule_for_user(user_email: str) -> dict[str, Any] | None:
    normalized = normalize_email(user_email)
    with connection() as conn:
        row = _fetchone(
            conn,
            """
            SELECT user_email, active, daily_at, timezone, resume_path, resume_uri, config_payload,
                   next_run_at, last_run_at, last_error, last_result, created_at, updated_at
            FROM scheduler_records
            WHERE user_email = ?
            """,
            (normalized,),
        )
    return _decode_schedule(row) if row else None


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
        from psycopg.types.json import Jsonb

        return tuple(Jsonb(json.loads(value)) if _looks_like_json(value) else value for value in params)
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


def _decode_schedule(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("config_payload", "last_result"):
        value = row.get(key)
        if isinstance(value, str) and value:
            row[key] = json.loads(value)
    return row


def _ensure_column(conn: Any, table: str, column: str, definition: str) -> None:
    try:
        if IS_POSTGRES:
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
            return
        columns = _fetchall(conn, f"PRAGMA table_info({table})")
        if any(row.get("name") == column for row in columns):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except Exception:
        # Existing deployments should continue to boot even if a best-effort
        # compatibility migration is unnecessary for the current schema.
        return


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
