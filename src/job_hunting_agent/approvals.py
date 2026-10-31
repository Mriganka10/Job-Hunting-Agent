"""Human approval before any recruiter email leaves the platform.

Lifecycle of one message::

    pending_approval --approve--> scheduled --(undo window ends)--> sending --> sent
          |                          |                                   \\--> failed
          \\--reject--> rejected      \\--undo--> pending_approval

Guardrails:
- Nothing is sent without an explicit approval of the exact subject and body.
- A per-user daily cap on sent messages (``JOB_AGENT_EMAIL_DAILY_CAP``, default 20).
- The same recruiter address is not emailed twice within
  ``JOB_AGENT_EMAIL_DUPLICATE_DAYS`` (default 30) days.
- An undo window (``JOB_AGENT_EMAIL_UNDO_SECONDS``, default 60) after approval.
- Every decision and every send is written to the audit log with the exact text.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import os
import re
import smtplib
import threading
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from . import ops_db
from .metrics import emit

logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[A-Z0-9._%+'-]+@[A-Z0-9.-]+\.[A-Z]{2,63}$", re.I)


class ApprovalError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def daily_cap() -> int:
    return max(1, int(os.getenv("JOB_AGENT_EMAIL_DAILY_CAP", "20")))


def undo_seconds() -> int:
    return max(0, int(os.getenv("JOB_AGENT_EMAIL_UNDO_SECONDS", "60")))


def duplicate_days() -> int:
    return max(0, int(os.getenv("JOB_AGENT_EMAIL_DUPLICATE_DAYS", "30")))


def approval_required() -> bool:
    """Approval is mandatory in the web app; only a local CLI operator may opt out."""
    return os.getenv("JOB_AGENT_REQUIRE_APPROVAL", "true").strip().lower() not in {"false", "0", "off", "no"}


def _start_of_day() -> float:
    now = time.time()
    return now - (now % 86400)


def queue_applications(user_email: str, run_id: int, applications: list[dict[str, Any]], *, resume_path: str = "", resume_uri: str = "") -> int:
    """Turn a run's "pending_approval" applications into outbox items."""
    queued = 0
    for application in applications:
        if application.get("status") != "pending_approval":
            continue
        job = application.get("job") or {}
        recipient = str(job.get("recruiter_email") or "").strip()
        body = str(application.get("draft_message") or "").strip()
        if not recipient or not EMAIL_RE.match(recipient) or not body:
            continue
        item_id = ops_db.outbox_add(
            user_email,
            run_id=run_id,
            job_key=f"{job.get('portal') or ''}:{job.get('source_id') or job.get('url') or ''}".lower(),
            portal=str(job.get("portal") or ""), title=str(job.get("title") or ""), company=str(job.get("company") or ""),
            job_url=str(job.get("url") or ""), recipient=recipient,
            subject=f"Application for {job.get('title') or 'the role'}"[:200], body=body,
            attachment_path=resume_path, attachment_uri=resume_uri,
        )
        if item_id:
            queued += 1
            ops_db.audit(user_email, "approval_queued", actor="system", target=str(item_id), detail={"recipient": recipient, "job": job.get("title")})
            emit("approval_queued", user_email=user_email, run_id=run_id)
    return queued


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    send_after = item.get("send_after")
    return {
        "id": item["id"], "run_id": item.get("run_id"), "status": item["status"], "title": item.get("title"),
        "company": item.get("company"), "portal": item.get("portal"), "job_url": item.get("job_url"),
        "recipient": item.get("recipient"), "subject": item.get("subject"), "body": item.get("body"),
        "error": item.get("error") or "", "created_ts": item.get("created_ts"), "sent_ts": item.get("sent_ts"),
        "undo_seconds_left": max(0, int(float(send_after) - now)) if item["status"] == "scheduled" and send_after else 0,
        "has_attachment": bool(item.get("attachment_path") or item.get("attachment_uri")),
    }


def overview(user_email: str) -> dict[str, Any]:
    items = ops_db.outbox_items(user_email, limit=60)
    used = ops_db.outbox_sent_count(user_email, _start_of_day())
    return {
        "items": [public_item(item) for item in items],
        "daily_cap": daily_cap(),
        "sent_today": used,
        "remaining_today": max(0, daily_cap() - used),
        "undo_seconds": undo_seconds(),
        "duplicate_window_days": duplicate_days(),
    }


def approve(user_email: str, item_id: int, *, subject: str | None, body: str | None, confirmed: bool) -> dict[str, Any]:
    item = ops_db.outbox_item(user_email, item_id)
    if not item:
        raise ApprovalError("Draft not found.", 404)
    if item["status"] != "pending_approval":
        raise ApprovalError(f"This draft is already {item['status'].replace('_', ' ')}.", 409)
    if not confirmed:
        raise ApprovalError("Confirm that you have reviewed the recipient and message before sending.", 400)
    final_subject = (subject if subject is not None else item["subject"]).strip()[:200]
    final_body = (body if body is not None else item["body"]).strip()
    if not final_subject or len(final_body) < 20:
        raise ApprovalError("Subject and message are required (message at least 20 characters).", 400)
    if len(final_body) > 8000:
        raise ApprovalError("Message is too long (8,000 characters maximum).", 400)
    if not EMAIL_RE.match(str(item["recipient"])):
        raise ApprovalError("Recipient email address is not valid.", 400)
    used = ops_db.outbox_sent_count(user_email, _start_of_day())
    if used >= daily_cap():
        emit("approval_blocked", user_email=user_email, reason="daily_cap")
        raise ApprovalError(f"Daily limit reached: {daily_cap()} recruiter emails per day. Approve the rest tomorrow.", 429)
    window = duplicate_days()
    if window and ops_db.outbox_recipient_recent(user_email, str(item["recipient"]), time.time() - window * 86400, exclude_id=item_id):
        emit("approval_blocked", user_email=user_email, reason="duplicate_recipient")
        raise ApprovalError(f"You already emailed {item['recipient']} in the last {window} days. This draft was not sent.", 409)
    now = time.time()
    if not ops_db.outbox_transition(user_email, item_id, ("pending_approval",), "scheduled", subject=final_subject, body=final_body,
                                    send_after=now + undo_seconds(), approved_ts=now, error=""):
        raise ApprovalError("This draft changed while you were reviewing it. Refresh and try again.", 409)
    edit_ratio = round(1 - difflib.SequenceMatcher(None, str(item["body"]), final_body).ratio(), 3)
    ops_db.audit(user_email, "approval_approved", target=str(item_id), detail={
        "recipient": item["recipient"], "subject": final_subject, "body": final_body,
        "body_sha256": hashlib.sha256(final_body.encode("utf-8")).hexdigest(), "edit_ratio": edit_ratio,
    })
    emit("approval_approved", user_email=user_email, edit_ratio=edit_ratio, decision_seconds=round(now - float(item["created_ts"] or now)))
    if undo_seconds() == 0:
        send_due()
    return public_item(ops_db.outbox_item(user_email, item_id) or item)


def undo(user_email: str, item_id: int) -> dict[str, Any]:
    item = ops_db.outbox_item(user_email, item_id)
    if not item:
        raise ApprovalError("Draft not found.", 404)
    if item["status"] != "scheduled" or float(item.get("send_after") or 0) <= time.time():
        raise ApprovalError("Too late to undo: the email is already being sent.", 409)
    if not ops_db.outbox_transition(user_email, item_id, ("scheduled",), "pending_approval", send_after=None, approved_ts=None):
        raise ApprovalError("Too late to undo: the email is already being sent.", 409)
    ops_db.audit(user_email, "approval_undone", target=str(item_id))
    emit("approval_undone", user_email=user_email)
    return public_item(ops_db.outbox_item(user_email, item_id) or item)


def reject(user_email: str, item_id: int, reason: str = "") -> dict[str, Any]:
    item = ops_db.outbox_item(user_email, item_id)
    if not item:
        raise ApprovalError("Draft not found.", 404)
    if not ops_db.outbox_transition(user_email, item_id, ("pending_approval",), "rejected", error=reason[:200]):
        raise ApprovalError("Only drafts waiting for approval can be rejected.", 409)
    ops_db.audit(user_email, "approval_rejected", target=str(item_id), detail={"reason": reason[:200]})
    emit("approval_rejected", user_email=user_email, reason=reason[:60], decision_seconds=round(time.time() - float(item["created_ts"] or time.time())))
    return public_item(ops_db.outbox_item(user_email, item_id) or item)


# ---------------------------------------------------------------------------
# Sending (claimed atomically, so several web tasks can run the loop safely)
# ---------------------------------------------------------------------------
def send_due(limit: int = 20) -> int:
    sent = 0
    for item in ops_db.outbox_due(limit=limit):
        if not ops_db.outbox_transition(item["user_email"], item["id"], ("scheduled",), "sending"):
            continue  # another task claimed it, or the user pressed undo
        try:
            message_id = deliver(item)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:160]}"
            ops_db.outbox_transition(item["user_email"], item["id"], ("sending",), "failed", error=error)
            ops_db.audit(item["user_email"], "approval_send_failed", actor="system", target=str(item["id"]), detail={"error": error})
            emit("approval_send_failed", user_email=item["user_email"], error=type(exc).__name__, count=1)
            continue
        ops_db.outbox_transition(item["user_email"], item["id"], ("sending",), "sent", sent_ts=time.time())
        ops_db.audit(item["user_email"], "approval_sent", actor="system", target=str(item["id"]), detail={
            "recipient": item["recipient"], "message_id": message_id,
            "body_sha256": hashlib.sha256(str(item["body"]).encode("utf-8")).hexdigest(),
        })
        emit("approval_sent", user_email=item["user_email"])
        sent += 1
    return sent


def deliver(item: dict[str, Any]) -> str:
    """Send through SMTP (or SES when JOB_AGENT_EMAIL_PROVIDER=ses). Returns a message id."""
    sender = os.getenv("JOB_AGENT_SMTP_FROM", "").strip() or os.getenv("JOB_AGENT_SES_FROM", "").strip()
    message = EmailMessage()
    message["Subject"] = str(item["subject"])
    message["From"] = sender or os.getenv("JOB_AGENT_SMTP_USERNAME", "")
    message["To"] = str(item["recipient"])
    message["Reply-To"] = str(item["user_email"])
    message.set_content(str(item["body"]))
    attachment = _attachment_path(item)
    if attachment:
        message.add_attachment(attachment.read_bytes(), maintype="application", subtype="octet-stream", filename=attachment.name)
    message_id = hashlib.sha1(f"{item['id']}:{item['recipient']}:{time.time()}".encode()).hexdigest()[:20]
    message["Message-ID"] = f"<{message_id}@job-hunting-agent>"
    if os.getenv("JOB_AGENT_EMAIL_PROVIDER", "smtp").strip().lower() == "ses":
        import boto3

        client = boto3.client("sesv2", region_name=os.getenv("JOB_AGENT_SES_REGION", os.getenv("AWS_REGION", "ap-south-1")))
        client.send_email(FromEmailAddress=message["From"], Destination={"ToAddresses": [str(item["recipient"])]},
                          Content={"Raw": {"Data": message.as_bytes()}})
        return message_id
    host = os.getenv("JOB_AGENT_SMTP_HOST", "")
    username = os.getenv("JOB_AGENT_SMTP_USERNAME", "")
    password = os.getenv("JOB_AGENT_SMTP_PASSWORD", "")
    if not all((host, username, password)):
        raise RuntimeError("Outgoing email is not configured (SMTP host, username and password).")
    with smtplib.SMTP(host, int(os.getenv("JOB_AGENT_SMTP_PORT", "587")), timeout=20) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)
    return message_id


def _attachment_path(item: dict[str, Any]) -> Path | None:
    path = Path(str(item.get("attachment_path") or ""))
    if str(path) not in {"", "."} and path.is_file():
        return path
    uri = str(item.get("attachment_uri") or "")
    if uri:
        from .storage import download_file

        return download_file(uri, Path("data") / "outbox-cache")
    return None


class OutboxSender:
    """Background loop that sends approved messages once their undo window ends."""

    def __init__(self, interval_seconds: float = 10.0) -> None:
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if os.getenv("JOB_AGENT_OUTBOX_SENDER", "on").strip().lower() in {"off", "false", "0"}:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="outbox-sender", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                send_due()
            except Exception:
                logger.exception("Outbox sender iteration failed")


SENDER = OutboxSender()
