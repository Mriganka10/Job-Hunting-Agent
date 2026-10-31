"""Storage for production guardrails, approvals, metrics and privacy.

These tables sit beside the original schema in ``db.py`` and reuse its
connection, so SQLite (local) and PostgreSQL (AWS) both work. Existing tables
are only extended with nullable/defaulted columns, so old deployments keep
booting and old rows keep working.

Timestamps in these tables are stored as epoch seconds (``ts`` columns). That
keeps range queries identical on SQLite and PostgreSQL. JSON values are passed
through :class:`J` so they are stored as JSONB on PostgreSQL and as text on
SQLite, without guessing from the first character of a string.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from datetime import datetime, timezone
from typing import Any

from . import db

OTP_MAX_ATTEMPTS = 5


class J:
    """Marks a value that must be stored as JSON."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value


def _params(params: tuple[Any, ...]) -> tuple[Any, ...]:
    converted: list[Any] = []
    for value in params:
        if isinstance(value, J):
            if db.IS_POSTGRES:
                from psycopg.types.json import Jsonb

                converted.append(Jsonb(value.value))
            else:
                converted.append(json.dumps(value.value, ensure_ascii=False))
        elif isinstance(value, bool) and not db.IS_POSTGRES:
            converted.append(int(value))
        else:
            converted.append(value)
    return tuple(converted)


def _q(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return conn.execute(sql.replace("?", "%s") if db.IS_POSTGRES else sql, _params(params))


def _one(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = _q(conn, sql, params).fetchone()
    return dict(row) if row else None


def _all(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in _q(conn, sql, params).fetchall()]


def _insert(conn: Any, sql: str, params: tuple[Any, ...]) -> int:
    if db.IS_POSTGRES:
        row = _q(conn, sql + " RETURNING id", params).fetchone()
        return int(dict(row)["id"])
    return int(_q(conn, sql, params).lastrowid)


def _json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def user_hash(email: str) -> str:
    """Stable pseudonymous id for metrics; never store raw emails in events."""
    return hashlib.sha256(f"job-agent-metrics:{db.normalize_email(email)}".encode("utf-8")).hexdigest()[:16] if email else ""


def utc_day(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc).strftime("%Y-%m-%d")


def init_ops_db() -> None:
    pk = "SERIAL PRIMARY KEY" if db.IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION" if db.IS_POSTGRES else "REAL"
    jtype = "JSONB" if db.IS_POSTGRES else "TEXT"
    statements = [
        f"CREATE TABLE IF NOT EXISTS rate_events (id {pk}, bucket TEXT NOT NULL, ts {real} NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_rate_events_bucket_ts ON rate_events(bucket, ts)",
        f"""CREATE TABLE IF NOT EXISTS audit_log (
              id {pk}, user_email TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
              target TEXT NOT NULL DEFAULT '', detail {jtype}, ts {real} NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_email, ts)",
        f"""CREATE TABLE IF NOT EXISTS application_outbox (
              id {pk}, user_email TEXT NOT NULL, run_id INTEGER, job_key TEXT NOT NULL,
              portal TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '',
              job_url TEXT NOT NULL DEFAULT '', recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
              attachment_path TEXT NOT NULL DEFAULT '', attachment_uri TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL, send_after {real}, approved_ts {real}, sent_ts {real},
              error TEXT NOT NULL DEFAULT '', created_ts {real} NOT NULL, updated_ts {real} NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_outbox_user ON application_outbox(user_email, status)",
        "CREATE INDEX IF NOT EXISTS idx_outbox_due ON application_outbox(status, send_after)",
        f"""CREATE TABLE IF NOT EXISTS metric_events (
              id {pk}, event TEXT NOT NULL, user_hash TEXT NOT NULL DEFAULT '', day TEXT NOT NULL,
              ts {real} NOT NULL, value {real}, props {jtype})""",
        "CREATE INDEX IF NOT EXISTS idx_metric_events_event_ts ON metric_events(event, ts)",
        "CREATE INDEX IF NOT EXISTS idx_metric_events_user ON metric_events(user_hash, ts)",
        f"""CREATE TABLE IF NOT EXISTS lead_feedback (
              id {pk}, user_email TEXT NOT NULL, run_id INTEGER NOT NULL, job_key TEXT NOT NULL,
              portal TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', verdict TEXT NOT NULL,
              reason TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', rank INTEGER, match_score INTEGER,
              ts {real} NOT NULL)""",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_feedback_unique ON lead_feedback(user_email, run_id, job_key)",
        f"""CREATE TABLE IF NOT EXISTS llm_usage (
              id {pk}, day TEXT NOT NULL, feature TEXT NOT NULL, user_hash TEXT NOT NULL DEFAULT '',
              input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
              cost_usd {real} NOT NULL DEFAULT 0, ok INTEGER NOT NULL DEFAULT 1, ts {real} NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_llm_usage_day ON llm_usage(day)",
        f"""CREATE TABLE IF NOT EXISTS content_reports (
              id {pk}, user_email TEXT NOT NULL, kind TEXT NOT NULL, item_id TEXT NOT NULL,
              reason TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open',
              ts {real} NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_content_reports_item ON content_reports(kind, item_id)",
    ]
    with db.connection() as conn:
        if db.IS_POSTGRES:
            conn.execute("SELECT pg_advisory_xact_lock(4815162343)")
        for statement in statements:
            conn.execute(statement)
        db._ensure_column(conn, "otp_codes", "attempts", "INTEGER NOT NULL DEFAULT 0")
        db._ensure_column(conn, "users", "consent_version", "TEXT NOT NULL DEFAULT ''")
        db._ensure_column(conn, "users", "consent_at", "TEXT")


# ---------------------------------------------------------------------------
# Rate limiting (sliding window, shared by every web/worker task via the DB)
# ---------------------------------------------------------------------------
def rate_hit(bucket: str, limit: int, window_seconds: int, *, now: float | None = None) -> tuple[bool, int]:
    """Record one hit; return (allowed, retry_after_seconds)."""
    now = time.time() if now is None else now
    since = now - window_seconds
    with db.connection() as conn:
        row = _one(conn, "SELECT COUNT(*) AS n, MIN(ts) AS oldest FROM rate_events WHERE bucket = ? AND ts > ?", (bucket, since)) or {}
        count = int(row.get("n") or 0)
        if count >= limit:
            oldest = float(row.get("oldest") or now)
            return False, max(1, int(oldest + window_seconds - now) + 1)
        _q(conn, "INSERT INTO rate_events (bucket, ts) VALUES (?, ?)", (bucket, now))
        if random.random() < 0.02:
            _q(conn, "DELETE FROM rate_events WHERE ts < ?", (now - 2 * 86400,))
    return True, 0


def rate_count(bucket: str, window_seconds: int) -> int:
    with db.connection() as conn:
        row = _one(conn, "SELECT COUNT(*) AS n FROM rate_events WHERE bucket = ? AND ts > ?", (bucket, time.time() - window_seconds)) or {}
    return int(row.get("n") or 0)


# ---------------------------------------------------------------------------
# OTP verification with an attempt limit
# ---------------------------------------------------------------------------
def verify_otp(email: str, code_hash: str, *, compare) -> str:
    """Check the newest unused code. Returns 'ok', 'invalid', 'expired' or 'locked'.

    Every wrong guess counts against the code; after ``OTP_MAX_ATTEMPTS`` the
    code is burned, so a 6-digit code cannot be brute-forced.
    """
    normalized = db.normalize_email(email)
    with db.connection() as conn:
        row = _one(
            conn,
            "SELECT id, code_hash, expires_at, attempts FROM otp_codes WHERE email = ? AND consumed = ? ORDER BY id DESC LIMIT 1",
            (normalized, False),
        )
        if not row:
            return "invalid"
        if db._parse_time(row["expires_at"]) < db.utcnow():
            _q(conn, "UPDATE otp_codes SET consumed = ? WHERE id = ?", (True, row["id"]))
            return "expired"
        attempts = int(row.get("attempts") or 0)
        if attempts >= OTP_MAX_ATTEMPTS:
            _q(conn, "UPDATE otp_codes SET consumed = ? WHERE id = ?", (True, row["id"]))
            return "locked"
        if compare(str(row["code_hash"]), code_hash):
            _q(conn, "UPDATE otp_codes SET consumed = ? WHERE id = ?", (True, row["id"]))
            result = "ok"
        else:
            attempts += 1
            _q(conn, "UPDATE otp_codes SET attempts = ?, consumed = ? WHERE id = ?", (attempts, attempts >= OTP_MAX_ATTEMPTS, row["id"]))
            result = "locked" if attempts >= OTP_MAX_ATTEMPTS else "invalid"
    if result == "ok":
        db.ensure_user(normalized)
    return result


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def audit(user_email: str, action: str, *, actor: str = "", target: str = "", detail: dict[str, Any] | None = None) -> None:
    normalized = db.normalize_email(user_email)
    with db.connection() as conn:
        _q(
            conn,
            "INSERT INTO audit_log (user_email, actor, action, target, detail, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (normalized, db.normalize_email(actor or user_email), action, target, J(detail or {}), time.time()),
        )


def audit_entries(user_email: str, limit: int = 100) -> list[dict[str, Any]]:
    with db.connection() as conn:
        rows = _all(
            conn,
            "SELECT id, actor, action, target, detail, ts FROM audit_log WHERE user_email = ? ORDER BY id DESC LIMIT ?",
            (db.normalize_email(user_email), int(limit)),
        )
    for row in rows:
        row["detail"] = _json(row.get("detail"), {})
    return rows


# ---------------------------------------------------------------------------
# Application outbox (human approval before anything reaches a recruiter)
# ---------------------------------------------------------------------------
OUTBOX_COLUMNS = (
    "id, user_email, run_id, job_key, portal, title, company, job_url, recipient, subject, body, attachment_path, "
    "attachment_uri, status, send_after, approved_ts, sent_ts, error, created_ts, updated_ts"
)


def outbox_add(user_email: str, *, run_id: int | None, job_key: str, portal: str, title: str, company: str,
               job_url: str, recipient: str, subject: str, body: str, attachment_path: str = "",
               attachment_uri: str = "") -> int | None:
    """Queue a message for approval. A job already queued or sent is not queued twice."""
    normalized = db.normalize_email(user_email)
    now = time.time()
    with db.connection() as conn:
        existing = _one(
            conn,
            "SELECT id FROM application_outbox WHERE user_email = ? AND job_key = ? AND status IN ('pending_approval', 'scheduled', 'sending', 'sent')",
            (normalized, job_key),
        )
        if existing:
            return None
        return _insert(
            conn,
            "INSERT INTO application_outbox (user_email, run_id, job_key, portal, title, company, job_url, recipient, subject, body, "
            "attachment_path, attachment_uri, status, send_after, approved_ts, sent_ts, error, created_ts, updated_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (normalized, run_id, job_key, portal, title, company, job_url, recipient.strip().lower(), subject, body,
             attachment_path, attachment_uri, "pending_approval", None, None, None, "", now, now),
        )


def outbox_items(user_email: str, *, statuses: tuple[str, ...] = (), limit: int = 100) -> list[dict[str, Any]]:
    params: list[Any] = [db.normalize_email(user_email)]
    clause = ""
    if statuses:
        clause = " AND status IN (" + ", ".join("?" for _ in statuses) + ")"
        params.extend(statuses)
    params.append(int(limit))
    with db.connection() as conn:
        return _all(conn, f"SELECT {OUTBOX_COLUMNS} FROM application_outbox WHERE user_email = ?{clause} ORDER BY id DESC LIMIT ?", tuple(params))


def outbox_item(user_email: str, item_id: int) -> dict[str, Any] | None:
    with db.connection() as conn:
        return _one(conn, f"SELECT {OUTBOX_COLUMNS} FROM application_outbox WHERE id = ? AND user_email = ?", (int(item_id), db.normalize_email(user_email)))


def outbox_transition(user_email: str, item_id: int, from_statuses: tuple[str, ...], to_status: str, **fields: Any) -> bool:
    """Atomically move an item between states; False when it was not in ``from_statuses``."""
    assignments = ["status = ?", "updated_ts = ?"]
    params: list[Any] = [to_status, time.time()]
    for key in ("subject", "body", "send_after", "approved_ts", "sent_ts", "error"):
        if key in fields:
            assignments.append(f"{key} = ?")
            params.append(fields[key])
    params.extend([int(item_id), db.normalize_email(user_email), *from_statuses])
    placeholders = ", ".join("?" for _ in from_statuses)
    with db.connection() as conn:
        cursor = _q(
            conn,
            f"UPDATE application_outbox SET {', '.join(assignments)} WHERE id = ? AND user_email = ? AND status IN ({placeholders})",
            tuple(params),
        )
        return (cursor.rowcount or 0) > 0


def outbox_due(now: float | None = None, limit: int = 20) -> list[dict[str, Any]]:
    with db.connection() as conn:
        return _all(
            conn,
            f"SELECT {OUTBOX_COLUMNS} FROM application_outbox WHERE status = 'scheduled' AND send_after <= ? ORDER BY send_after LIMIT ?",
            (time.time() if now is None else now, int(limit)),
        )


def outbox_sent_count(user_email: str, since_ts: float) -> int:
    """Messages sent or about to be sent (scheduled/sending) since ``since_ts``."""
    with db.connection() as conn:
        row = _one(
            conn,
            "SELECT COUNT(*) AS n FROM application_outbox WHERE user_email = ? AND status IN ('scheduled', 'sending', 'sent') AND approved_ts >= ?",
            (db.normalize_email(user_email), since_ts),
        ) or {}
    return int(row.get("n") or 0)


def outbox_recipient_recent(user_email: str, recipient: str, since_ts: float, *, exclude_id: int | None = None) -> bool:
    with db.connection() as conn:
        row = _one(
            conn,
            "SELECT id FROM application_outbox WHERE user_email = ? AND recipient = ? AND status IN ('scheduled', 'sending', 'sent') "
            "AND approved_ts >= ? AND id <> ? LIMIT 1",
            (db.normalize_email(user_email), recipient.strip().lower(), since_ts, int(exclude_id or 0)),
        )
    return row is not None


# ---------------------------------------------------------------------------
# Metric events and feedback
# ---------------------------------------------------------------------------
def record_event(event: str, *, user_email: str = "", value: float | None = None, props: dict[str, Any] | None = None,
                 ts: float | None = None) -> None:
    ts = time.time() if ts is None else ts
    with db.connection() as conn:
        _q(
            conn,
            "INSERT INTO metric_events (event, user_hash, day, ts, value, props) VALUES (?, ?, ?, ?, ?, ?)",
            (event, user_hash(user_email), utc_day(ts), ts, value, J(props or {})),
        )


def events_since(since_ts: float, *, events: tuple[str, ...] = (), user_email: str = "", limit: int = 50000) -> list[dict[str, Any]]:
    params: list[Any] = [since_ts]
    clause = ""
    if events:
        clause += " AND event IN (" + ", ".join("?" for _ in events) + ")"
        params.extend(events)
    if user_email:
        clause += " AND user_hash = ?"
        params.append(user_hash(user_email))
    params.append(int(limit))
    with db.connection() as conn:
        rows = _all(conn, f"SELECT event, user_hash, day, ts, value, props FROM metric_events WHERE ts >= ?{clause} ORDER BY ts LIMIT ?", tuple(params))
    for row in rows:
        row["props"] = _json(row.get("props"), {})
    return rows


def save_lead_feedback(user_email: str, *, run_id: int, job_key: str, portal: str, title: str, verdict: str,
                       reason: str, note: str, rank: int | None, match_score: int | None) -> None:
    normalized = db.normalize_email(user_email)
    now = time.time()
    with db.connection() as conn:
        existing = _one(conn, "SELECT id FROM lead_feedback WHERE user_email = ? AND run_id = ? AND job_key = ?", (normalized, int(run_id), job_key))
        if existing:
            _q(
                conn,
                "UPDATE lead_feedback SET verdict = ?, reason = ?, note = ?, rank = ?, match_score = ?, ts = ? WHERE id = ?",
                (verdict, reason, note, rank, match_score, now, existing["id"]),
            )
            return
        _q(
            conn,
            "INSERT INTO lead_feedback (user_email, run_id, job_key, portal, title, verdict, reason, note, rank, match_score, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (normalized, int(run_id), job_key, portal, title, verdict, reason, note, rank, match_score, now),
        )


def lead_feedback_for_run(user_email: str, run_id: int) -> dict[str, dict[str, Any]]:
    with db.connection() as conn:
        rows = _all(conn, "SELECT job_key, verdict, reason FROM lead_feedback WHERE user_email = ? AND run_id = ?", (db.normalize_email(user_email), int(run_id)))
    return {row["job_key"]: {"verdict": row["verdict"], "reason": row["reason"]} for row in rows}


def lead_feedback_since(since_ts: float) -> list[dict[str, Any]]:
    with db.connection() as conn:
        return _all(conn, "SELECT run_id, job_key, portal, title, verdict, reason, note, rank, match_score, ts FROM lead_feedback WHERE ts >= ? ORDER BY ts", (since_ts,))


def save_content_report(user_email: str, *, kind: str, item_id: str, reason: str, note: str) -> None:
    with db.connection() as conn:
        _q(
            conn,
            "INSERT INTO content_reports (user_email, kind, item_id, reason, note, status, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (db.normalize_email(user_email), kind, item_id, reason, note, "open", time.time()),
        )


def content_reports_since(since_ts: float, kind: str = "") -> list[dict[str, Any]]:
    with db.connection() as conn:
        if kind:
            return _all(conn, "SELECT kind, item_id, reason, note, status, ts FROM content_reports WHERE ts >= ? AND kind = ? ORDER BY ts", (since_ts, kind))
        return _all(conn, "SELECT kind, item_id, reason, note, status, ts FROM content_reports WHERE ts >= ? ORDER BY ts", (since_ts,))


# ---------------------------------------------------------------------------
# LLM usage (spend caps)
# ---------------------------------------------------------------------------
def record_llm_usage(feature: str, *, user_email: str = "", input_tokens: int, output_tokens: int, cost_usd: float, ok: bool) -> None:
    now = time.time()
    with db.connection() as conn:
        _q(
            conn,
            "INSERT INTO llm_usage (day, feature, user_hash, input_tokens, output_tokens, cost_usd, ok, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (utc_day(now), feature, user_hash(user_email), int(input_tokens), int(output_tokens), float(cost_usd), int(bool(ok)), now),
        )


def llm_spend(day: str | None = None, *, user_email: str = "") -> float:
    day = day or utc_day()
    with db.connection() as conn:
        if user_email:
            row = _one(conn, "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_usage WHERE day = ? AND user_hash = ?", (day, user_hash(user_email)))
        else:
            row = _one(conn, "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_usage WHERE day = ?", (day,))
    return float((row or {}).get("total") or 0.0)


def llm_usage_since(since_ts: float) -> list[dict[str, Any]]:
    with db.connection() as conn:
        return _all(conn, "SELECT day, feature, input_tokens, output_tokens, cost_usd, ok FROM llm_usage WHERE ts >= ?", (since_ts,))


# ---------------------------------------------------------------------------
# Consent, export and deletion (DPDP Act 2023)
# ---------------------------------------------------------------------------
def record_consent(user_email: str, version: str) -> None:
    db.ensure_user(user_email)
    with db.connection() as conn:
        _q(conn, "UPDATE users SET consent_version = ?, consent_at = ? WHERE email = ?",
           (version, db.utcnow().isoformat(), db.normalize_email(user_email)))


def consent_status(user_email: str) -> dict[str, Any]:
    with db.connection() as conn:
        row = _one(conn, "SELECT consent_version, consent_at FROM users WHERE email = ?", (db.normalize_email(user_email),))
    return {"version": (row or {}).get("consent_version") or "", "at": str((row or {}).get("consent_at") or "")}


USER_TABLES = (
    ("user_profiles", "user_email"), ("run_records", "user_email"), ("application_records", "user_email"),
    ("scheduler_records", "user_email"), ("mock_interview_records", "user_email"), ("mock_test_records", "user_email"),
    ("application_outbox", "user_email"), ("lead_feedback", "user_email"), ("content_reports", "user_email"),
    ("otp_codes", "email"), ("email_verifications", "email"),
)


def delete_user_rows(user_email: str) -> dict[str, int]:
    """Remove every row that belongs to one user, including their audit trail.

    Metric events and LLM usage rows only carry a one-way user hash, so they
    are kept for aggregate statistics.
    """
    normalized = db.normalize_email(user_email)
    removed: dict[str, int] = {}
    with db.connection() as conn:
        for table, column in USER_TABLES:
            cursor = _q(conn, f"DELETE FROM {table} WHERE {column} = ?", (normalized,))
            removed[table] = int(cursor.rowcount or 0)
        cursor = _q(conn, "DELETE FROM users WHERE email = ?", (normalized,))
        removed["users"] = int(cursor.rowcount or 0)
        _q(conn, "DELETE FROM audit_log WHERE user_email = ?", (normalized,))
    return removed


def inactive_users(cutoff_iso: str, limit: int = 500) -> list[str]:
    """Users whose last login is older than ``cutoff_iso`` (ISO-8601, UTC)."""
    with db.connection() as conn:
        rows = _all(conn, "SELECT email, last_login_at, created_at FROM users ORDER BY id LIMIT ?", (int(limit) * 20,))
    cutoff = db._parse_time(cutoff_iso)
    stale: list[str] = []
    for row in rows:
        reference = row.get("last_login_at") or row.get("created_at")
        if reference and db._parse_time(reference) < cutoff:
            stale.append(str(row["email"]))
        if len(stale) >= limit:
            break
    return stale
