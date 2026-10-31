"""Consent, data export, deletion and retention (India's DPDP Act 2023).

- Consent: a resume is processed only after the user accepts the notice for
  the current ``CONSENT_VERSION``; the version and time are stored.
- Access: ``export_user_data`` returns everything stored about the user.
- Erasure: ``delete_user_data`` removes database rows, local files, S3 objects
  and the scheduled run.
- Retention: ``purge_inactive_users`` erases accounts with no login for
  ``JOB_AGENT_RETENTION_DAYS`` (default 180) days. The worker and the web app
  run it at most once a day.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import db, ops_db
from .metrics import emit

logger = logging.getLogger(__name__)
CONSENT_VERSION = os.getenv("JOB_AGENT_CONSENT_VERSION", "2026-10")
PURPOSE = (
    "We use your resume and profile only to score ATS readiness, find matching jobs, prepare tailored resumes and "
    "application drafts, and run practice tests and interviews for you. Recruiter emails are sent only after you approve "
    "each one. You can download or delete your data at any time."
)


def retention_days() -> int:
    return max(30, int(os.getenv("JOB_AGENT_RETENTION_DAYS", "180")))


def has_consent(user_email: str) -> bool:
    return ops_db.consent_status(user_email).get("version") == CONSENT_VERSION


def give_consent(user_email: str) -> dict[str, Any]:
    ops_db.record_consent(user_email, CONSENT_VERSION)
    ops_db.audit(user_email, "consent_given", detail={"version": CONSENT_VERSION})
    emit("consent_given", user_email=user_email, version=CONSENT_VERSION)
    return {"version": CONSENT_VERSION, **ops_db.consent_status(user_email)}


def user_data_dir(user_email: str, data_root: Path = Path("data")) -> Path:
    key = hashlib.sha256(db.normalize_email(user_email).encode("utf-8")).hexdigest()[:20]
    return data_root / "users" / key


def export_user_data(user_email: str) -> dict[str, Any]:
    email = db.normalize_email(user_email)
    profile = db.user_profile(email) or {}
    runs = []
    for run in db.latest_runs(email, limit=50):
        payload = dict(run.get("payload") or {})
        payload.pop("_config_snapshot", None)
        improved = dict(payload.get("improved_resume") or {})
        improved.pop("_resume_snapshot", None)
        payload["improved_resume"] = improved
        runs.append({"id": run.get("id"), "generated_at": run.get("generated_at"), "ats_score": run.get("ats_score"), "payload": payload})
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "email": email,
        "consent": ops_db.consent_status(email),
        "profile": profile.get("profile_payload") or {},
        "resume_name": profile.get("resume_name") or "",
        "runs": runs,
        "mock_tests": db.latest_mock_tests(email, limit=200, completed_only=False),
        "mock_interviews": db.latest_mock_interviews(email, limit=200),
        "application_outbox": ops_db.outbox_items(email, limit=500),
        "audit_log": ops_db.audit_entries(email, limit=1000),
        "schedule": db.schedule_for_user(email),
    }


def delete_user_data(user_email: str, *, data_root: Path = Path("data")) -> dict[str, Any]:
    email = db.normalize_email(user_email)
    result: dict[str, Any] = {"email_hash": ops_db.user_hash(email)}
    try:
        from .scheduler_backend import delete_user_schedule, uses_eventbridge_scheduler

        db.disable_schedule(email)
        if uses_eventbridge_scheduler():
            delete_user_schedule(email)
    except Exception as exc:  # deletion continues; the schedule row is removed below
        logger.warning("Schedule removal during deletion failed: %s", type(exc).__name__)
    local_dir = user_data_dir(email, data_root)
    if local_dir.exists():
        shutil.rmtree(local_dir, ignore_errors=True)
    result["local_files_removed"] = not local_dir.exists()
    try:
        from .storage import delete_prefix

        result["s3_objects_removed"] = delete_prefix(f"uploads/{email}") + delete_prefix(f"artifacts/{email}")
    except Exception as exc:
        result["s3_objects_removed"] = 0
        result["s3_error"] = type(exc).__name__
    result["rows_removed"] = ops_db.delete_user_rows(email)
    emit("account_deleted", user_email=email, reason="user_request")
    return result


def purge_inactive_users(*, now: datetime | None = None, data_root: Path = Path("data")) -> list[str]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days())
    purged = []
    for email in ops_db.inactive_users(cutoff.isoformat()):
        delete_user_data(email, data_root=data_root)
        purged.append(ops_db.user_hash(email))
    if purged:
        emit("retention_purge", count=len(purged), retention_days=retention_days())
    return purged


class RetentionJob:
    """Run the retention purge at most once a day per process."""

    def __init__(self) -> None:
        self._last = 0.0
        self._lock = threading.Lock()

    def maybe_run(self) -> None:
        if os.getenv("JOB_AGENT_RETENTION", "on").strip().lower() in {"off", "false", "0"}:
            return
        with self._lock:
            if time.time() - self._last < 86400:
                return
            self._last = time.time()
        try:
            purge_inactive_users()
        except Exception:
            logger.exception("Retention purge failed")


RETENTION = RetentionJob()
