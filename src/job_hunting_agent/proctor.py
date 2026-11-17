"""Shared, server-owned lifecycle for proctored practice assessments.

Browser observations are useful signals, not proof of misconduct. Video and audio
remain in the browser; this module stores only typed events and warning counts.
"""
from __future__ import annotations

import time
from typing import Any

from . import db, ops_db

KINDS = {"mock_test", "mock_interview"}
SIGNALS = {"tab_hidden", "fullscreen_exit", "camera_lost", "microphone_lost",
           "face_absent", "multiple_faces", "face_obscured", "poor_lighting", "device_visible"}
HEARTBEAT_TIMEOUT_SECONDS = 60


def _row(conn: Any, user_email: str, kind: str, assessment_id: int, *, lock: bool = False) -> dict[str, Any] | None:
    suffix = " FOR UPDATE" if lock and db.IS_POSTGRES else ""
    return ops_db._one(conn,
        "SELECT status, warnings, last_seen, reason FROM assessment_proctor "
        "WHERE user_email = ? AND kind = ? AND assessment_id = ?" + suffix,
        (db.normalize_email(user_email), kind, assessment_id))


def start(user_email: str, kind: str, assessment_id: int) -> None:
    if kind not in KINDS or assessment_id <= 0:
        raise ValueError("Invalid assessment")
    with db.connection() as conn:
        ops_db._q(conn,
            "INSERT INTO assessment_proctor (user_email, kind, assessment_id, status, warnings, last_seen) "
            "VALUES (?, ?, ?, 'active', 0, ?)",
            (db.normalize_email(user_email), kind, assessment_id, time.time()))


def state(user_email: str, kind: str, assessment_id: int) -> dict[str, Any] | None:
    with db.connection() as conn:
        row = _row(conn, user_email, kind, assessment_id)
    if not row:
        return None
    return {"status": row["status"], "warnings": int(row["warnings"]), "reason": row["reason"]}


def require_active(user_email: str, kind: str, assessment_id: int) -> None:
    item = heartbeat(user_email, kind, assessment_id)
    if not item or item["status"] != "active":
        raise ValueError("This assessment is no longer active.")


def heartbeat(user_email: str, kind: str, assessment_id: int) -> dict[str, Any] | None:
    now = time.time()
    with db.connection() as conn:
        if not db.IS_POSTGRES:
            conn.execute("BEGIN IMMEDIATE")
        row = _row(conn, user_email, kind, assessment_id, lock=True)
        if not row:
            return None
        status = row["status"]
        reason = row["reason"]
        if status == "active" and now - float(row["last_seen"]) > HEARTBEAT_TIMEOUT_SECONDS:
            status, reason = "terminated", "Monitoring connection was lost."
            ops_db._q(conn, "UPDATE assessment_proctor SET status = ?, reason = ? WHERE user_email = ? AND kind = ? AND assessment_id = ?",
                      (status, reason, db.normalize_email(user_email), kind, assessment_id))
        if status == "active":
            ops_db._q(conn, "UPDATE assessment_proctor SET last_seen = ? WHERE user_email = ? AND kind = ? AND assessment_id = ?",
                      (now, db.normalize_email(user_email), kind, assessment_id))
        return {"status": status, "warnings": int(row["warnings"]), "reason": reason}


def report(user_email: str, kind: str, assessment_id: int, *, event_id: str, signal: str,
           confidence: float | None = None) -> dict[str, Any] | None:
    if kind not in KINDS or signal not in SIGNALS or not event_id or len(event_id) > 80:
        raise ValueError("Invalid monitoring event")
    now = time.time()
    normalized = db.normalize_email(user_email)
    with db.connection() as conn:
        if not db.IS_POSTGRES:
            conn.execute("BEGIN IMMEDIATE")
        row = _row(conn, normalized, kind, assessment_id, lock=True)
        if not row:
            return None
        if row["status"] != "active":
            return {"status": row["status"], "warnings": int(row["warnings"]), "reason": row["reason"]}
        if now - float(row["last_seen"]) > HEARTBEAT_TIMEOUT_SECONDS:
            reason = "Monitoring connection was lost."
            ops_db._q(conn, "UPDATE assessment_proctor SET status = 'terminated', reason = ? WHERE user_email = ? AND kind = ? AND assessment_id = ?",
                      (reason, normalized, kind, assessment_id))
            return {"status": "terminated", "warnings": int(row["warnings"]), "reason": reason}
        duplicate = ops_db._one(conn,
            "SELECT id FROM assessment_proctor_events WHERE user_email = ? AND kind = ? AND assessment_id = ? AND event_id = ?",
            (normalized, kind, assessment_id, event_id))
        if duplicate:
            return {"status": "active", "warnings": int(row["warnings"]), "reason": ""}
        recent = ops_db._one(conn,
            "SELECT ts FROM assessment_proctor_events WHERE user_email = ? AND kind = ? AND assessment_id = ? AND signal = ? ORDER BY ts DESC LIMIT 1",
            (normalized, kind, assessment_id, signal))
        # Repeated frames and browser event bursts describe one incident.
        count = not recent or now - float(recent["ts"]) >= 10
        warnings = int(row["warnings"]) + int(count)
        status = "terminated" if warnings > 2 else "active"
        action = "terminated" if status == "terminated" else ("warning" if count else "duplicate")
        reason = f"Assessment ended after a third monitoring warning ({signal.replace('_', ' ')})." if status == "terminated" else ""
        ops_db._q(conn,
            "INSERT INTO assessment_proctor_events (user_email, kind, assessment_id, event_id, signal, confidence, action, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (normalized, kind, assessment_id, event_id, signal, confidence, action, now))
        ops_db._q(conn,
            "UPDATE assessment_proctor SET status = ?, warnings = ?, reason = ?, last_seen = ? "
            "WHERE user_email = ? AND kind = ? AND assessment_id = ?",
            (status, warnings, reason, now, normalized, kind, assessment_id))
        return {"status": status, "warnings": warnings, "reason": reason, "action": action, "signal": signal}


def finish(user_email: str, kind: str, assessment_id: int) -> None:
    with db.connection() as conn:
        ops_db._q(conn,
            "UPDATE assessment_proctor SET status = 'completed' WHERE user_email = ? AND kind = ? AND assessment_id = ? AND status = 'active'",
            (db.normalize_email(user_email), kind, assessment_id))


def events(user_email: str, limit: int = 500) -> list[dict[str, Any]]:
    with db.connection() as conn:
        return ops_db._all(conn,
            "SELECT kind, assessment_id, signal, confidence, action, ts FROM assessment_proctor_events "
            "WHERE user_email = ? ORDER BY ts DESC LIMIT ?",
            (db.normalize_email(user_email), limit))
