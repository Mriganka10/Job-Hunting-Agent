from __future__ import annotations

import shutil
import hashlib
import hmac
import base64
import json
import os
import re
import secrets
import smtplib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from xml.sax.saxutils import escape as xml_escape
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from fastapi import BackgroundTasks, Body, Cookie, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .agent import JobHuntingAgent
from .config import DEFAULT_PORTALS, AppConfig, ApplicationConfig, EmailConfig, SearchConfig
from .db import (
    active_schedules,
    best_mock_test_percent,
    complete_mock_test,
    create_mock_test,
    latest_mock_tests,
    mock_test_question_history,
    mock_test_record,
    complete_mock_interview_session,
    create_mock_interview_session,
    disable_schedule,
    email_verification,
    ensure_user,
    init_db,
    latest_runs,
    latest_mock_interviews,
    mock_interview_session,
    mock_interview_question_history,
    mutate_run_payload,
    normalize_email,
    record_run,
    run_for_user,
    save_email_verification,
    save_user_profile,
    save_otp,
    save_schedule,
    schedule_for_user,
    update_schedule_status,
    user_profile,
)
from .models import AtsReport, CandidateProfile, JobLead, Resume
from .job_pagination import DEFAULT_JOB_PAGE_SIZE, paginate_jobs
from .interview_evaluator import evaluate_interview
from .interview_questions import build_question_groups, interview_level, select_question_sequence
from .interview_coding import CODING_SLOTS, add_coding_questions, is_technical_interview
from .interview_job_context import build_job_fit_group, job_interview_focus, select_job_interview_sequence
from .partner_sources import REQUEST_CONTEXT, RequestContext, active_job_sources, partner_status
from .portals import portal_search_links
from .mock_test import DIFFICULTIES as MOCK_TEST_DIFFICULTIES, LENGTHS as MOCK_TEST_LENGTHS, build_mock_test, grade_mock_test, profile_terms, public_questions
from .interview_evaluator import evaluate_interview
from .performance_cache import cached_document, document_cache_key
from .resume_builder import write_base_resume, write_tailored_resume
from .resume_validation import change_summary
from .scheduler_backend import delete_user_schedule, upsert_user_schedule, uses_eventbridge_scheduler
from .storage import StoredObject, download_file, mirror_artifacts, presigned_download_url, upload_file
from . import approvals, metrics, ops_db, privacy
from .guardrails import RateLimited, enforce as enforce_limit
from .llm_client import start_run_budget
from fastapi.responses import JSONResponse

app = FastAPI(title="Job Hunting Agent")
ADMIN_EMAILS = {item.strip().lower() for item in os.getenv("JOB_AGENT_ADMIN_EMAILS", "").split(",") if item.strip()}
REQUIRE_CONSENT = os.getenv("JOB_AGENT_REQUIRE_CONSENT", "true").strip().lower() not in {"false", "0", "off", "no"}


@app.exception_handler(RateLimited)
def _rate_limited(_: Request, exc: RateLimited) -> JSONResponse:
    metrics.emit("rate_limited", persist=False, limit=exc.name)
    minutes = max(1, round(exc.retry_after / 60))
    return JSONResponse(
        {"detail": f"Too many requests. Please try again in about {minutes} minute{'s' if minutes != 1 else ''}.", "retry_after": exc.retry_after},
        status_code=429,
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(approvals.ApprovalError)
def _approval_error(_: Request, exc: approvals.ApprovalError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


@app.middleware("http")
async def _observe_requests(request: Request, call_next):
    started = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
    finally:
        route = request.scope.get("route")
        metrics.observe_request(getattr(route, "path", "unmatched"), status, time.monotonic() - started)
    # Baseline security headers for every page and API response.
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), payment=()")
    if COOKIE_SECURE:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


TRUSTED_PROXY_HOPS = max(1, int(os.getenv("JOB_AGENT_TRUSTED_PROXY_HOPS", "2")))  # CloudFront + ALB


def _client_ip(request: Request | None) -> str:
    """Client IP for rate limits, read from the right of X-Forwarded-For.

    The leftmost entries can be forged by the caller; CloudFront appends the
    real viewer IP and the ALB appends CloudFront's, so with the default two
    trusted hops the viewer IP is second from the right.
    """
    if request is None:
        return ""
    parts = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
    if parts:
        return parts[-TRUSTED_PROXY_HOPS if len(parts) >= TRUSTED_PROXY_HOPS else 0][:64]
    return (request.client.host if request.client else "")[:64]


def require_admin(session_cookie: str | None) -> str:
    user_email = require_user(session_cookie)
    if user_email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user_email

DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploads"
STATIC_DIR = Path(__file__).resolve().parent / "static"
SESSION_COOKIE = "job_agent_session"
SESSION_MAX_AGE_SECONDS = int(os.getenv("JOB_AGENT_SESSION_MAX_AGE_SECONDS", str(60 * 60 * 12)))
OTP_TTL_MINUTES = int(os.getenv("JOB_AGENT_OTP_TTL_MINUTES", "10"))
APP_SECRET = os.getenv("JOB_AGENT_SECRET_KEY", "local-dev-change-me")
COOKIE_SECURE = os.getenv("JOB_AGENT_COOKIE_SECURE", "false").lower() == "true"
DEV_RETURN_OTP = os.getenv("JOB_AGENT_DEV_RETURN_OTP", "true").lower() == "true"
EMAIL_PROVIDER = os.getenv("JOB_AGENT_EMAIL_PROVIDER", "smtp").strip().lower()
SES_REGION = os.getenv("JOB_AGENT_SES_REGION", os.getenv("AWS_REGION", "ap-south-1"))
AZURE_SPEECH_KEY = os.getenv("JOB_AGENT_AZURE_SPEECH_KEY", "").strip()
AZURE_SPEECH_REGION = os.getenv("JOB_AGENT_AZURE_SPEECH_REGION", "").strip()
EMAIL_PATTERN = re.compile(
    r"^(?=.{6,254}$)(?!.*\.\.)[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$",
    re.IGNORECASE,
)
if COOKIE_SECURE and APP_SECRET == "local-dev-change-me":
    raise RuntimeError("Set JOB_AGENT_SECRET_KEY to a long random value before running with secure cookies.")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
init_db()

DOCUMENT_WORKERS = max(1, int(os.getenv("JOB_AGENT_DOCUMENT_WORKERS", "2")))
DOCUMENT_EXECUTOR = ThreadPoolExecutor(max_workers=DOCUMENT_WORKERS, thread_name_prefix="resume-render")
_document_tasks: set[str] = set()
_document_tasks_lock = threading.Lock()
_interview_start_lock = threading.Lock()
_mock_test_start_lock = threading.Lock()


class DailyScheduler:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.last_result: dict | None = None
        self.last_run_at: str | None = None
        self.last_error: str | None = None
        self.created_at: str | None = None
        self.next_run_at: str | None = None
        self.daily_at: str | None = None
        self.timezone_name: str = "UTC"
        self.resume_path: str | None = None
        self.resume_uri: str = ""
        self.config: AppConfig | None = None
        self.user_email: str | None = None
        self.history: list[dict] = []
        self._externally_active = False

    def start(
        self,
        resume_path: str,
        config: AppConfig,
        daily_at: str,
        user_email: str,
        timezone_name: str = "UTC",
        resume_uri: str = "",
        persist: bool = True,
    ) -> None:
        hour, minute = _parse_hhmm(daily_at)
        zone = _timezone(timezone_name)
        with self._lock:
            self.stop()
            self._stop_event = threading.Event()
            self.resume_path = resume_path
            self.resume_uri = resume_uri
            self.config = config
            self.user_email = normalize_email(user_email)
            self.daily_at = daily_at
            self.timezone_name = zone.key
            self.created_at = datetime.now().isoformat(timespec="seconds")
            self.last_result = None
            self.last_run_at = None
            self.last_error = None
            self.next_run_at = _next_run_time(hour, minute, zone).isoformat(timespec="minutes")
            if persist:
                save_schedule(
                    self.user_email,
                    daily_at=daily_at,
                    timezone_name=self.timezone_name,
                    resume_path=resume_path,
                    resume_uri=resume_uri,
                    config_payload=_config_payload(config),
                    next_run_at=self.next_run_at,
                )
                if uses_eventbridge_scheduler():
                    upsert_user_schedule(self.user_email, daily_at, self.timezone_name)
            if uses_eventbridge_scheduler():
                self._externally_active = True
                return
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1)
        self._thread = None
        self._externally_active = False
        self.next_run_at = None

    @property
    def is_running(self) -> bool:
        return bool(
            (self._thread and self._thread.is_alive())
            or self._externally_active
        )

    def snapshot(self) -> dict:
        return {
            "running": self.is_running,
            "daily_at": self.daily_at,
            "timezone": self.timezone_name,
            "next_run_at": self.next_run_at,
            "created_at": self.created_at,
            "last_run_at": self.last_run_at,
            "last_error": self.last_error,
            "resume_path": self.resume_path,
            "last_result": self.last_result,
            "history": self.history[-1:],
        }

    def _loop(self) -> None:
        assert self.config is not None
        assert self.resume_path is not None
        assert self.daily_at is not None
        assert self.user_email is not None
        hour, minute = _parse_hhmm(self.daily_at)
        zone = _timezone(self.timezone_name)
        while not self._stop_event.is_set():
            next_run = _next_run_time(hour, minute, zone)
            self.next_run_at = next_run.isoformat(timespec="minutes")
            update_schedule_status(self.user_email, next_run_at=self.next_run_at)
            wait_seconds = max(1, (next_run - datetime.now(zone)).total_seconds())
            if self._stop_event.wait(wait_seconds):
                return
            started_at = datetime.now().isoformat(timespec="seconds")
            try:
                resume_path = self._resolved_resume_path()
                self.last_result = run_agent(resume_path, self.config, trigger="scheduled", user_email=self.user_email)
                self.last_run_at = self.last_result["generated_at"]
                self.last_error = None
                self.history.append(_history_item("scheduled", started_at, self.last_result))
                update_schedule_status(
                    self.user_email,
                    last_run_at=self.last_run_at,
                    last_error="",
                    last_result=self.last_result,
                )
            except Exception as exc:
                self.last_error = str(exc)
                self.history.append(
                    {
                        "trigger": "scheduled",
                        "started_at": started_at,
                        "finished_at": datetime.now().isoformat(timespec="seconds"),
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                update_schedule_status(self.user_email, last_error=str(exc))

    def _resolved_resume_path(self) -> str:
        assert self.resume_path is not None
        path = Path(self.resume_path)
        if path.exists():
            return str(path)
        if self.resume_uri:
            assert self.user_email is not None
            restored = download_file(self.resume_uri, _user_upload_dir(self.user_email))
            self.resume_path = str(restored)
            return str(restored)
        return str(path)


class SchedulerRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._schedulers: dict[str, DailyScheduler] = {}

    def get(self, user_email: str) -> DailyScheduler | None:
        with self._lock:
            return self._schedulers.get(normalize_email(user_email))

    def get_or_create(self, user_email: str) -> DailyScheduler:
        normalized = normalize_email(user_email)
        with self._lock:
            return self._schedulers.setdefault(normalized, DailyScheduler())

    def stop(self, user_email: str) -> dict:
        scheduler = self.get(user_email)
        if not scheduler:
            return _empty_scheduler_snapshot()
        scheduler.stop()
        return scheduler.snapshot()

    def stop_all(self) -> None:
        with self._lock:
            schedulers = list(self._schedulers.values())
        for scheduler in schedulers:
            scheduler.stop()


schedulers = SchedulerRegistry()


def start_background_guards() -> None:
    """Send approved emails after their undo window; purge expired accounts daily."""
    approvals.SENDER.start()
    threading.Thread(target=privacy.RETENTION.maybe_run, name="retention", daemon=True).start()


@app.on_event("startup")
def restore_active_schedule() -> None:
    start_background_guards()
    for saved in active_schedules(limit=1000):
        try:
            scheduler = schedulers.get_or_create(saved["user_email"])
            scheduler.start(
                saved["resume_path"],
                _config_from_payload(saved["config_payload"]),
                saved["daily_at"],
                saved["user_email"],
                timezone_name=saved.get("timezone") or "UTC",
                resume_uri=saved.get("resume_uri") or "",
                persist=False,
            )
            scheduler.last_run_at = saved.get("last_run_at")
            scheduler.last_error = saved.get("last_error")
            scheduler.last_result = saved.get("last_result")
            if scheduler.last_result:
                scheduler.history.append(_history_item("scheduled", scheduler.last_run_at or "", scheduler.last_result))
        except Exception as exc:
            update_schedule_status(saved["user_email"], last_error=f"Schedule restore failed: {exc}")


def _empty_scheduler_snapshot() -> dict:
    return {
        "running": False,
        "daily_at": None,
        "timezone": "UTC",
        "next_run_at": None,
        "created_at": None,
        "last_run_at": None,
        "last_error": None,
        "resume_path": None,
        "last_result": None,
        "history": [],
    }


def current_user_email(session_cookie: str | None) -> str | None:
    if not session_cookie:
        return None
    try:
        payload_b64, signature = session_cookie.split(".", 1)
        expected = hmac.new(APP_SECRET.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(_pad_b64(payload_b64)).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    issued_at = int(payload.get("iat", 0))
    if issued_at + SESSION_MAX_AGE_SECONDS < int(time.time()):
        return None
    email = payload.get("email") if isinstance(payload, dict) else None
    return normalize_email(email) if email else None


def require_user(session_cookie: str | None) -> str:
    user_email = current_user_email(session_cookie)
    if not user_email:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user_email


def _hash_otp(email: str, otp: str) -> str:
    return hmac.new(APP_SECRET.encode("utf-8"), f"{normalize_email(email)}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()


def _validated_email(email: str) -> str:
    normalized = normalize_email(email)
    local_part = normalized.split("@", 1)[0] if "@" in normalized else ""
    if (
        not EMAIL_PATTERN.fullmatch(normalized)
        or len(local_part) > 64
        or local_part.startswith(".")
        or local_part.endswith(".")
        or any(char.isspace() for char in normalized)
    ):
        raise HTTPException(status_code=400, detail="Enter a valid email address like name@example.com.")
    return normalized


def _session_token(email: str) -> str:
    payload = json.dumps({"email": normalize_email(email), "iat": int(time.time())}, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(APP_SECRET.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def _pad_b64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("ascii")


def _send_otp_email(email: str, otp: str) -> bool:
    if EMAIL_PROVIDER == "ses":
        return _send_otp_email_ses(email, otp)
    smtp_host = os.getenv("JOB_AGENT_SMTP_HOST", "")
    smtp_user = os.getenv("JOB_AGENT_SMTP_USERNAME", "")
    smtp_password = os.getenv("JOB_AGENT_SMTP_PASSWORD", "")
    from_email = os.getenv("JOB_AGENT_SMTP_FROM", smtp_user)
    if not all((smtp_host, smtp_user, smtp_password, from_email)):
        # Never write sign-in codes to production logs.
        if DEV_RETURN_OTP:
            print(f"[job-agent] OTP for {email}: {otp}")
        return False
    message = EmailMessage()
    message["Subject"] = "Your Job Hunting Agent sign-in code"
    message["From"] = from_email
    message["To"] = email
    message.set_content(f"Your Job Hunting Agent OTP is {otp}. It expires in {OTP_TTL_MINUTES} minutes.")
    with smtplib.SMTP(smtp_host, int(os.getenv("JOB_AGENT_SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)
    return True


def _send_otp_email_ses(email: str, otp: str) -> bool:
    from_email = os.getenv("JOB_AGENT_SES_FROM", os.getenv("JOB_AGENT_SMTP_FROM", "")).strip()
    if not from_email:
        print("[job-agent] SES OTP delivery is not configured." + (f" OTP for {email}: {otp}" if DEV_RETURN_OTP else ""))
        return False

    subject = "Your Job Hunting Agent sign-in code"
    body = (
        f"Your Job Hunting Agent OTP is {otp}.\n\n"
        f"It expires in {OTP_TTL_MINUTES} minutes. If you did not request this code, you can ignore this email."
    )
    try:
        client = _ses_client()
        client.send_email(
            FromEmailAddress=from_email,
            Destination={"ToAddresses": [email]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                }
            },
        )
    except Exception as exc:
        print(f"[job-agent] SES OTP delivery failed for {email}: {exc}")
        return False
    return True


def _ses_sender_configured() -> bool:
    return bool(os.getenv("JOB_AGENT_SES_FROM", os.getenv("JOB_AGENT_SMTP_FROM", "")).strip())


def _ses_email_status(email: str) -> str:
    try:
        response = _ses_client().get_email_identity(EmailIdentity=normalize_email(email))
        status = str(response.get("VerificationStatus") or "NOT_STARTED")
    except Exception as exc:
        print(f"[job-agent] SES verification status check failed for {email}: {exc}")
        status = "UNKNOWN"
    save_email_verification(email, status, detail="SES identity status checked.")
    return status


def _ses_email_verified(email: str) -> bool:
    if _ses_email_status(email).upper() == "SUCCESS":
        ensure_user(normalize_email(email))
        return True
    return False


def _start_ses_email_verification(email: str) -> dict:
    normalized = normalize_email(email)
    if EMAIL_PROVIDER != "ses":
        save_email_verification(normalized, "SUCCESS", detail="Non-SES local provider; verification bypassed for local/dev mode.")
        ensure_user(normalized)
        return {"status": "verified", "email": normalized, "provider": EMAIL_PROVIDER}
    try:
        _ses_client().create_email_identity(EmailIdentity=normalized)
        save_email_verification(normalized, "PENDING", detail="AWS SES verification email requested.")
    except Exception as exc:
        status = _ses_email_status(normalized)
        if status.upper() == "SUCCESS":
            ensure_user(normalized)
            return {"status": "verified", "email": normalized, "provider": "ses"}
        save_email_verification(normalized, status, detail=f"SES verification request did not complete: {exc}")
        if status.upper() in {"PENDING", "TEMPORARY_FAILURE"}:
            return {"status": "pending", "email": normalized, "provider": "ses", "ses_status": status}
        raise HTTPException(status_code=503, detail="Unable to start AWS SES email verification. Please try again later.") from exc
    return {"status": "pending", "email": normalized, "provider": "ses", "ses_status": "PENDING"}


def _ses_client():
    import boto3

    return boto3.client("sesv2", region_name=SES_REGION)


def _localized(html: str, lang: str | None) -> HTMLResponse:
    """Render a page in the language chosen in the picker (cookie ``jha_lang``)."""
    from .pages import localize_document

    response = HTMLResponse(localize_document(html, lang or ""))
    response.headers["Content-Language"] = (lang or "en") if (lang or "en") in {"en", "hi", "ar"} else "en"
    response.headers["Vary"] = "Cookie"
    return response


@app.get("/", response_class=HTMLResponse)
def index(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE), jha_lang: str | None = Cookie(default=None)) -> HTMLResponse:
    user_email = current_user_email(job_agent_session)
    if not user_email:
        return RedirectResponse("/login", status_code=303)
    return _localized(_page(user_email, _profile_for_user(user_email)), jha_lang)


@app.get("/mock-interview", response_class=HTMLResponse)
def mock_interview_page(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE), jha_lang: str | None = Cookie(default=None)) -> HTMLResponse:
    user_email = current_user_email(job_agent_session)
    if not user_email:
        return RedirectResponse("/login", status_code=303)
    return _localized(_mock_interview_page(user_email), jha_lang)


@app.get("/mock-test", response_class=HTMLResponse)
def mock_test_page(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE), jha_lang: str | None = Cookie(default=None)) -> HTMLResponse:
    user_email = current_user_email(job_agent_session)
    if not user_email:
        return RedirectResponse("/login", status_code=303)
    return _localized(_mock_test_page(user_email), jha_lang)


@app.get("/login", response_class=HTMLResponse)
def login_page(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE), jha_lang: str | None = Cookie(default=None)) -> HTMLResponse:
    if current_user_email(job_agent_session):
        return RedirectResponse("/", status_code=303)
    return _localized(_login_page(), jha_lang)


@app.get("/register", response_class=HTMLResponse)
def register_page(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE), jha_lang: str | None = Cookie(default=None)) -> HTMLResponse:
    if current_user_email(job_agent_session):
        return RedirectResponse("/", status_code=303)
    return _localized(_register_page(), jha_lang)


@app.post("/api/auth/request-otp")
def request_otp(request: Request, email: Annotated[str, Form()] = "") -> dict:
    normalized = _validated_email(email)
    enforce_limit("otp_request_ip", _client_ip(request))
    enforce_limit("otp_request_email", normalized)
    if EMAIL_PROVIDER == "ses" and not DEV_RETURN_OTP:
        if not _ses_sender_configured():
            raise HTTPException(status_code=503, detail="OTP email delivery is not configured or failed. Please try again later.")
        if not _ses_email_verified(normalized):
            raise HTTPException(
                status_code=403,
                detail="This email is not verified yet. Use New User Registration first, then request OTP after clicking the AWS verification link.",
            )
    otp = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    save_otp(normalized, _hash_otp(normalized, otp), expires_at)
    sent = _send_otp_email(normalized, otp)
    metrics.emit("otp_requested", user_email=normalized, delivered=bool(sent))
    if not sent and not DEV_RETURN_OTP:
        raise HTTPException(status_code=503, detail="OTP email delivery is not configured or failed. Please try again later.")
    response = {
        "status": "sent",
        "email": normalized,
        "delivery": "email" if sent else "server-log",
        "expires_in_minutes": OTP_TTL_MINUTES,
    }
    if DEV_RETURN_OTP and not sent:
        response["dev_otp"] = otp
    return response


@app.post("/api/auth/register-email")
def register_email(request: Request, email: Annotated[str, Form()] = "") -> dict:
    normalized = _validated_email(email)
    enforce_limit("register_ip", _client_ip(request))
    current = email_verification(normalized)
    status = (current or {}).get("status", "")
    if status.upper() == "SUCCESS" or (EMAIL_PROVIDER == "ses" and _ses_email_verified(normalized)):
        ensure_user(normalized)
        return {"status": "verified", "email": normalized, "message": "Email is already verified. You can return to login and request an OTP."}
    result = _start_ses_email_verification(normalized)
    result["message"] = (
        "AWS SES verification email requested. Open that email and click the verification link, "
        "then return to login and request OTP."
    )
    return result


@app.post("/api/auth/verify")
def verify_otp(request: Request, email: Annotated[str, Form()] = "", otp: Annotated[str, Form()] = "") -> HTMLResponse:
    normalized = _validated_email(email)
    enforce_limit("otp_verify_ip", _client_ip(request))
    outcome = ops_db.verify_otp(normalized, _hash_otp(normalized, otp.strip()), compare=hmac.compare_digest)
    if outcome != "ok":
        metrics.emit("otp_locked" if outcome == "locked" else "login_failed", user_email=normalized, outcome=outcome)
        if outcome == "locked":
            raise HTTPException(status_code=429, detail="Too many wrong codes. This code is now blocked; request a new OTP.")
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    metrics.emit("login_ok", user_email=normalized)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        _session_token(normalized),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )
    return response


@app.post("/api/auth/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> JSONResponse:
    """Readiness for the load balancer: the database must answer."""
    from .db import connection

    try:
        with connection() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        return JSONResponse({"status": "unavailable", "database": type(exc).__name__}, status_code=503)
    return JSONResponse({"status": "ok", "database": "ok", "outbox_sender": approvals.SENDER._thread is not None})


@app.get("/api/dashboard")
def dashboard(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    runs = [_run_with_payload_id(run) for run in latest_runs(user_email, limit=1)]
    latest_run = runs[0] if runs else None
    scheduler = schedulers.get(user_email)
    scheduler_snapshot = scheduler.snapshot() if scheduler else _persisted_scheduler_snapshot(user_email)
    scheduler_snapshot["history"] = [_run_history_item(latest_run)] if latest_run else []
    profile = _profile_for_user(user_email)
    return {
        "profile": profile,
        "latest_run": latest_run,
        "scheduler": scheduler_snapshot,
        "portal_search_links": portal_search_links(
            _split_csv(profile.get("target_roles", "")), _split_csv(profile.get("locations", "")),
            float(profile.get("experience_years") or 0),
        ),
        "has_consent": privacy.has_consent(user_email),
    }


@app.get("/api/runs")
def runs(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    return {"runs": [_run_with_payload_id(run) for run in latest_runs(user_email, limit=1)]}


@app.get("/api/runs/{run_id}/jobs")
def paginated_run_jobs(
    run_id: int,
    cursor: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=25)] = DEFAULT_JOB_PAGE_SIZE,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user_email = require_user(job_agent_session)
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    payload = run.get("payload") or {}
    try:
        page = paginate_jobs(
            list(payload.get("jobs") or []),
            run_id=run_id,
            secret=APP_SECRET,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": run_id, **page}


@app.get("/api/mock-interview/questions")
def mock_interview_questions(
    job_id: str = Query(default=""),
    run_id: int = Query(default=0),
    job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    user_email = require_user(job_agent_session)
    profile = _profile_for_user(user_email)
    latest = next(iter(latest_runs(user_email, limit=1)), None)
    payload = (latest or {}).get("payload") or {}
    interview = _mock_interview_payload(profile, payload)
    job = _mock_test_job(user_email, job_id.strip(), run_id or None) if job_id.strip() else None
    if job_id.strip() and job is None:
        raise HTTPException(status_code=404, detail="Job lead not found in your recent runs.")
    if job is not None:
        interview = _job_interview_payload(job, interview)
    # The same job leads the Mock Test offers, so both features stay in step.
    interview["jobs"] = [_mock_test_job_summary(item, item_run_id) for item_run_id, item in _mock_test_candidate_jobs(user_email)]
    return interview


@app.post("/api/mock-interview/start")
def start_mock_interview(
    payload: Annotated[dict, Body()],
    job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    user_email = require_user(job_agent_session)
    enforce_limit("mock_interview", user_email)
    profile = _profile_for_user(user_email)
    latest = next(iter(latest_runs(user_email, limit=1)), None)
    latest_payload = (latest or {}).get("payload") or {}
    interview = _mock_interview_payload(profile, latest_payload)
    job_id = str(payload.get("job_id") or "").strip()
    job = _mock_test_job(user_email, job_id, int(payload.get("run_id") or 0) or None) if job_id else None
    if job_id and job is None:
        raise HTTPException(status_code=404, detail="Job lead not found in your recent runs.")
    if job is not None:
        interview = _job_interview_payload(job, interview)
    region = str(payload.get("region") or "India")
    voice = _accent_for_region(region)
    accent = voice["label"]
    requested_limit = max(4, min(int(payload.get("question_limit") or 8), 12))
    interview_mode = str(payload.get("interview_mode") or _interview_mode_for_limit(requested_limit)).strip().lower()
    mode_limits = {"quick": 5, "standard": 8, "deep": 10}
    if interview_mode not in mode_limits:
        raise HTTPException(status_code=400, detail="Interview mode must be quick, standard, or deep.")
    question_limit = mode_limits[interview_mode]
    # Keep history lookup and reservation together so two simultaneous starts in
    # this process cannot receive the same unseen set.
    with _interview_start_lock:
        history = mock_interview_question_history(user_email)
        if interview.get("job_fit_group"):
            questions = select_job_interview_sequence(
                interview["job_fit_group"], interview["groups"], question_limit, interview_mode, previous_questions=history,
            )
        else:
            questions = _interview_question_sequence(
                interview["groups"],
                question_limit,
                interview_mode,
                previous_questions=history,
            )
        # Technical roles: real coding problems at the candidate's level.
        questions = add_coding_questions(
            questions, roles=tuple(interview["roles"]), skills=tuple(interview["skills"]),
            level=str(interview.get("level") or "mid"), mode=interview_mode, previous_questions=history,
            seed=secrets.token_hex(8),
        )
        session_id = create_mock_interview_session(
            user_email,
            region=region,
            accent=accent,
            roles=tuple(interview["roles"]),
            skills=tuple(interview["skills"]),
            questions=questions,
            job_id=job_id if job else "",
            job_title=str((job or {}).get("title") or ""),
            company=str((job or {}).get("company") or ""),
        )
    metrics.emit("mock_interview_started", user_email=user_email, job_specific=bool(job), mode=interview_mode,
                 coding_questions=sum(1 for item in questions if item.get("answer_mode") == "code"))
    return {
        "session_id": session_id,
        "region": region,
        "accent": accent,
        "voice": _accent_for_region(region),
        "tts_provider": "azure" if AZURE_SPEECH_KEY and AZURE_SPEECH_REGION else "browser",
        "interview_mode": interview_mode,
        "level": interview.get("level", "mid"),
        "roles": interview["roles"],
        "skills": interview["skills"],
        "job": interview.get("job"),
        "questions": questions,
        "selection": {
            "new_questions": sum(not question["previously_asked"] for question in questions),
            "reused_questions": sum(question["previously_asked"] for question in questions),
            "history_questions_considered": len(history),
        },
    }


@app.post("/api/mock-interview/complete")
def complete_mock_interview(
    payload: Annotated[dict, Body()],
    job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    user_email = require_user(job_agent_session)
    session_id = int(payload.get("session_id") or 0)
    answers = payload.get("answers") or []
    if not session_id:
        raise HTTPException(status_code=400, detail="Interview session id is required.")
    if not isinstance(answers, list):
        raise HTTPException(status_code=400, detail="Interview answers must be a list.")
    session = mock_interview_session(user_email, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    session_questions = session.get("questions") or []
    scorecard = _score_mock_interview(
        answers,
        session_questions,
        roles=tuple(session.get("roles") or ()),
        skills=tuple(session.get("skills") or ()),
        interview_mode=_interview_mode_for_limit(len(session_questions)),
    )
    saved = complete_mock_interview_session(
        user_email,
        session_id,
        answers=answers,
        score=scorecard["score"],
        feedback=scorecard,
    )
    metrics.emit(
        "mock_interview_completed", user_email=user_email, value=float(scorecard.get("score") or 0),
        job_specific=bool(session.get("job_id")), answered=int(scorecard.get("answered") or 0),
        coding_questions=sum(1 for item in session_questions if item.get("answer_mode") == "code"),
        llm_score=scorecard.get("llm_score"), local_score=scorecard.get("local_score"),
    )
    return {"session": saved, "scorecard": scorecard}


@app.get("/api/mock-interview/history")
def mock_interview_history(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    return {"sessions": latest_mock_interviews(user_email, limit=3)}


@app.get("/api/mock-test/options")
def mock_test_options(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    """Job leads the user can take a test for, newest run first."""
    user_email = require_user(job_agent_session)
    profile = _profile_for_user(user_email)
    return {
        "jobs": [_mock_test_job_summary(job, run_id) for run_id, job in _mock_test_candidate_jobs(user_email)],
        "profile": {"target_roles": profile_terms(profile.get("target_roles")), "skills": profile_terms(profile.get("skills"))},
        "lengths": {name: count for name, count in MOCK_TEST_LENGTHS.items()},
        "difficulties": list(MOCK_TEST_DIFFICULTIES),
    }


@app.post("/api/mock-test/start")
def start_mock_test(
    payload: Annotated[dict, Body()],
    job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    user_email = require_user(job_agent_session)
    enforce_limit("mock_test", user_email)
    length = str(payload.get("length") or "standard").strip().lower()
    difficulty = str(payload.get("difficulty") or "mixed").strip().lower()
    if length not in MOCK_TEST_LENGTHS:
        raise HTTPException(status_code=400, detail="Test length must be quick, standard, or full.")
    if difficulty not in MOCK_TEST_DIFFICULTIES:
        raise HTTPException(status_code=400, detail="Difficulty must be mixed, easy, medium, or hard.")
    job_id = str(payload.get("job_id") or "").strip()
    run_id = int(payload.get("run_id") or 0) or None
    job: dict | None = None
    if job_id:
        job = _mock_test_job(user_email, job_id, run_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job lead not found in your recent runs.")
    profile = _profile_for_user(user_email)
    with _mock_test_start_lock:
        test = build_mock_test(
            job,
            profile,
            length=length,
            difficulty=difficulty,
            seen_question_ids=mock_test_question_history(user_email),
            seed=secrets.token_hex(8),
        )
        test_id = create_mock_test(
            user_email,
            run_id=run_id if job else None,
            job_id=job_id,
            job_title=str((job or {}).get("title") or "General practice"),
            company=str((job or {}).get("company") or ""),
            length=length,
            difficulty=difficulty,
            topics=test["topics"],
            questions=test["questions"],
            time_limit_seconds=test["time_limit_seconds"],
        )
    record = mock_test_record(user_email, test_id) or {}
    metrics.emit("mock_test_started", user_email=user_email, job_specific=bool(job), length=length, difficulty=difficulty,
                 coding_questions=sum(1 for item in test["questions"] if item.get("kind") == "code"))
    return _mock_test_client_payload(record)


@app.post("/api/mock-test/submit")
def submit_mock_test(
    payload: Annotated[dict, Body()],
    job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    user_email = require_user(job_agent_session)
    test_id = int(payload.get("test_id") or 0)
    if not test_id:
        raise HTTPException(status_code=400, detail="Test id is required.")
    record = mock_test_record(user_email, test_id)
    if not record:
        raise HTTPException(status_code=404, detail="Mock test not found.")
    if record.get("status") == "completed":
        # A test is graded once; resubmitting returns the original scorecard.
        return {**_mock_test_client_payload(record), "already_submitted": True}
    answers = payload.get("answers") or {}
    if not isinstance(answers, (dict, list)):
        raise HTTPException(status_code=400, detail="Answers must be an object of question id to option index.")
    # Elapsed time is measured on the server from the stored start time, so a
    # paused or edited browser clock cannot hide an over-time submission.
    started = _parse_iso_time(record.get("started_at"))
    elapsed = (datetime.now(timezone.utc) - started).total_seconds() if started else float(payload.get("elapsed_seconds") or 0)
    job = _mock_test_job(user_email, str(record.get("job_id") or ""), record.get("run_id")) if record.get("job_id") else None
    previous_best = best_mock_test_percent(user_email, str(record.get("job_id") or ""), exclude_id=test_id) if record.get("job_id") else None
    scorecard = grade_mock_test(
        record.get("questions") or [],
        answers,
        elapsed_seconds=elapsed,
        time_limit_seconds=int(record.get("time_limit_seconds") or 0),
        question_seconds=payload.get("question_seconds") if isinstance(payload.get("question_seconds"), dict) else None,
        job=job or {"title": record.get("job_title")},
        previous_best=previous_best,
    )
    stored_answers = {item["id"]: item["selected_index"] for item in scorecard["review"]}
    saved = complete_mock_test(user_email, test_id, answers=stored_answers, scorecard=scorecard) or record
    metrics.emit("mock_test_completed", user_email=user_email, value=float(scorecard.get("percent") or 0),
                 job_specific=bool(record.get("job_id")), questions=int(scorecard.get("total") or 0),
                 timed_out=bool((scorecard.get("time") or {}).get("submitted_after_time_limit")))
    return _mock_test_client_payload(saved)


@app.get("/api/mock-test/history")
def mock_test_history(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    return {"tests": [_mock_test_history_item(record) for record in latest_mock_tests(user_email, limit=10)]}


@app.get("/api/mock-test/{test_id}")
def mock_test_detail(test_id: int, job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    record = mock_test_record(user_email, test_id)
    if not record:
        raise HTTPException(status_code=404, detail="Mock test not found.")
    return _mock_test_client_payload(record)


# ---------------------------------------------------------------------------
# Human-in-the-loop approval queue for recruiter emails
# ---------------------------------------------------------------------------
@app.get("/api/approvals")
def list_approvals(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    return approvals.overview(require_user(job_agent_session))


@app.post("/api/approvals/{item_id}/approve")
def approve_application(item_id: int, payload: Annotated[dict, Body()], job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    subject = payload.get("subject")
    body = payload.get("body")
    item = approvals.approve(
        user_email, item_id,
        subject=str(subject) if subject is not None else None,
        body=str(body) if body is not None else None,
        confirmed=payload.get("confirm") is True,
    )
    return {"item": item, **{key: value for key, value in approvals.overview(user_email).items() if key != "items"}}


@app.post("/api/approvals/{item_id}/undo")
def undo_application(item_id: int, job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    return {"item": approvals.undo(require_user(job_agent_session), item_id)}


@app.post("/api/approvals/{item_id}/reject")
def reject_application(item_id: int, payload: Annotated[dict | None, Body()] = None, job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    reason = str((payload or {}).get("reason") or "")
    return {"item": approvals.reject(require_user(job_agent_session), item_id, reason)}


# ---------------------------------------------------------------------------
# Feedback that becomes live quality labels
# ---------------------------------------------------------------------------
LEAD_FEEDBACK_REASONS = {"role", "location", "seniority", "skills", "salary", "company", "duplicate", "expired", "other", ""}


def _run_job(user_email: str, run_id: int, job_id: str) -> tuple[dict, int]:
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    for rank, job in enumerate((run.get("payload") or {}).get("jobs") or [], start=1):
        if isinstance(job, dict) and _mock_test_job_id(job) == job_id:
            return job, rank
    raise HTTPException(status_code=404, detail="Job lead not found in this run.")


@app.post("/api/runs/{run_id}/feedback")
def lead_feedback(run_id: int, payload: Annotated[dict, Body()], job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    enforce_limit("feedback", user_email)
    verdict = str(payload.get("verdict") or "").strip().lower()
    reason = str(payload.get("reason") or "").strip().lower()
    if verdict not in {"relevant", "not_relevant"}:
        raise HTTPException(status_code=400, detail="Verdict must be relevant or not_relevant.")
    if reason not in LEAD_FEEDBACK_REASONS:
        raise HTTPException(status_code=400, detail="Unknown reason.")
    job_id = str(payload.get("job_id") or "").strip().lower()
    job, rank = _run_job(user_email, run_id, job_id)
    ops_db.save_lead_feedback(
        user_email, run_id=run_id, job_key=job_id, portal=str(job.get("portal") or ""), title=str(job.get("title") or ""),
        verdict=verdict, reason=reason if verdict == "not_relevant" else "", note=str(payload.get("note") or "")[:300],
        rank=rank, match_score=int(job.get("match_score") or 0),
    )
    metrics.emit("lead_feedback", user_email=user_email, run_id=run_id, verdict=verdict, reason=reason, rank=rank,
                 portal=job.get("portal"), not_relevant=int(verdict == "not_relevant"))
    return {"status": "saved", "job_id": job_id, "verdict": verdict, "reason": reason}


@app.get("/api/runs/{run_id}/feedback")
def run_feedback(run_id: int, job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    return {"feedback": ops_db.lead_feedback_for_run(user_email, run_id)}


@app.post("/api/events/lead-click")
def lead_click(payload: Annotated[dict, Body()], job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    enforce_limit("feedback", user_email)
    metrics.emit(
        "lead_click", user_email=user_email, run_id=int(payload.get("run_id") or 0),
        rank=int(payload.get("rank") or 0), portal=str(payload.get("portal") or "")[:40],
    )
    return {"status": "ok"}


@app.post("/api/mock-interview/{session_id}/rating")
def rate_interview_feedback(session_id: int, payload: Annotated[dict, Body()], job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    enforce_limit("feedback", user_email)
    if not mock_interview_session(user_email, session_id):
        raise HTTPException(status_code=404, detail="Interview session not found.")
    try:
        rating = int(payload.get("rating"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Rating must be 1 to 5.") from None
    if not 1 <= rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be 1 to 5.")
    unfair = payload.get("unfair") is True
    comment = str(payload.get("comment") or "")[:500]
    if unfair:
        ops_db.save_content_report(user_email, kind="interview_feedback", item_id=str(session_id), reason="unfair", note=comment)
    metrics.emit("interview_feedback_rating", user_email=user_email, rating=rating, unfair=unfair)
    return {"status": "saved", "rating": rating, "unfair": unfair}


@app.post("/api/mock-test/report-question")
def report_mock_test_question(payload: Annotated[dict, Body()], job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    enforce_limit("feedback", user_email)
    record = mock_test_record(user_email, int(payload.get("test_id") or 0))
    question_id = str(payload.get("question_id") or "")
    if not record or not any(str(item.get("id")) == question_id for item in record.get("questions") or []):
        raise HTTPException(status_code=404, detail="Question not found in your test.")
    reason = str(payload.get("reason") or "wrong_answer")[:40]
    ops_db.save_content_report(user_email, kind="mock_test_question", item_id=question_id, reason=reason, note=str(payload.get("note") or "")[:500])
    metrics.emit("question_reported", user_email=user_email, reason=reason)
    return {"status": "reported"}


# ---------------------------------------------------------------------------
# Privacy (DPDP Act 2023): consent, export, deletion, audit trail
# ---------------------------------------------------------------------------
@app.get("/api/account/privacy")
def account_privacy(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    return {
        "consent": ops_db.consent_status(user_email), "current_version": privacy.CONSENT_VERSION,
        "has_consent": privacy.has_consent(user_email), "purpose": privacy.PURPOSE, "retention_days": privacy.retention_days(),
    }


@app.post("/api/account/consent")
def account_consent(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    return privacy.give_consent(require_user(job_agent_session))


@app.get("/api/account/export")
def account_export(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> Response:
    user_email = require_user(job_agent_session)
    ops_db.audit(user_email, "data_exported")
    body = json.dumps(privacy.export_user_data(user_email), ensure_ascii=False, indent=2, default=str)
    return Response(body, media_type="application/json", headers={"Content-Disposition": 'attachment; filename="job-hunting-agent-my-data.json"', "Cache-Control": "no-store"})


@app.get("/api/account/audit")
def account_audit(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    return {"entries": ops_db.audit_entries(require_user(job_agent_session), limit=100)}


@app.post("/api/account/delete")
def account_delete(payload: Annotated[dict, Body()], job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> JSONResponse:
    user_email = require_user(job_agent_session)
    enforce_limit("account_delete", user_email)
    if normalize_email(str(payload.get("confirm_email") or "")) != user_email:
        raise HTTPException(status_code=400, detail="Type your email address exactly to confirm deletion.")
    scheduler = schedulers.get(user_email)
    if scheduler:
        scheduler.stop()
    result = privacy.delete_user_data(user_email, data_root=DATA_DIR)
    response = JSONResponse({"status": "deleted", "detail": result})
    response.delete_cookie(SESSION_COOKIE)
    return response


# ---------------------------------------------------------------------------
# Admin: production metrics and alerts
# ---------------------------------------------------------------------------
@app.get("/api/admin/metrics")
def admin_metrics(days: int = Query(default=7, ge=1, le=90), job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    require_admin(job_agent_session)
    return metrics.summary(days)


@app.get("/admin/metrics", response_class=HTMLResponse)
def admin_metrics_page(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE), jha_lang: str | None = Cookie(default=None)) -> HTMLResponse:
    user_email = current_user_email(job_agent_session)
    if not user_email:
        return RedirectResponse("/login", status_code=303)
    if user_email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required.")
    from .pages import admin_metrics_page as render

    return _localized(render(user_email), jha_lang)


@app.get("/progress", response_class=HTMLResponse)
def progress_page(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE), jha_lang: str | None = Cookie(default=None)) -> HTMLResponse:
    user_email = current_user_email(job_agent_session)
    if not user_email:
        return RedirectResponse("/login", status_code=303)
    from .pages import progress_page as render

    return _localized(render(user_email, is_admin=user_email in ADMIN_EMAILS), jha_lang)


@app.get("/api/progress/report")
def progress_report(
    period: str = Query(default="weekly"),
    job_id: str = Query(default=""),
    tz: str = Query(default="Asia/Kolkata"),
    job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    """Daily or weekly Mock Test and Mock Interview report, optionally for one job."""
    from .progress_reports import PERIODS, build_report

    user_email = require_user(job_agent_session)
    if period not in PERIODS:
        raise HTTPException(status_code=400, detail="Period must be daily or weekly.")
    return build_report(user_email, period=period, job_id=job_id.strip().lower()[:300], tz=tz[:64])


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE), jha_lang: str | None = Cookie(default=None)) -> HTMLResponse:
    from .pages import privacy_page as render

    user_email = current_user_email(job_agent_session) or ""
    return _localized(render(user_email, privacy.PURPOSE, privacy.retention_days(), privacy.CONSENT_VERSION, is_admin=user_email in ADMIN_EMAILS), jha_lang)


@app.post("/api/run")
async def run_now(
    background_tasks: BackgroundTasks,
    request: Request,
    resume: Annotated[UploadFile | None, File()] = None,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    linkedin_profile_url: Annotated[str, Form()] = "",
    naukri_profile_url: Annotated[str, Form()] = "",
    target_roles: Annotated[str, Form()] = "",
    locations: Annotated[str, Form()] = "",
    skills: Annotated[str, Form()] = "",
    experience_years: Annotated[str, Form()] = "",
    job_description: Annotated[str, Form()] = "",
    application_mode: Annotated[str, Form()] = "draft",
    max_jobs_per_portal: Annotated[int, Form()] = 10,
    daily_at: Annotated[str, Form()] = "",
    daily_timezone: Annotated[str, Form()] = "UTC",
    start_daily: Annotated[bool, Form()] = False,
    consent: Annotated[bool, Form()] = False,
) -> dict:
    user_email = require_user(job_agent_session)
    _require_consent(user_email, consent)
    years = _require_profile_fields(name=name, phone=phone, target_roles=target_roles, locations=locations,
                                    skills=skills, experience_years=experience_years, max_jobs_per_portal=max_jobs_per_portal)
    enforce_limit("run", user_email)
    stored_resume = await resolve_resume(resume, user_email)
    config = _config_for_user(user_email, build_config_from_form(
        name=name,
        email=user_email,
        phone=phone,
        linkedin_profile_url=linkedin_profile_url,
        naukri_profile_url=naukri_profile_url,
        target_roles=target_roles,
        locations=locations,
        skills=skills,
        experience_years=years,
        job_description=job_description,
        application_mode=application_mode,
        max_jobs_per_portal=max_jobs_per_portal,
    ))
    _save_profile(user_email, config, stored_resume)
    try:
        # The agent does blocking network and CPU work. Running it in the thread
        # pool keeps this async endpoint from freezing every other request
        # (login, dashboards, other users) on the same worker while it runs.
        # Some partner APIs (Careerjet) require the searching user's IP and
        # browser. The context variable is copied into the worker threads.
        REQUEST_CONTEXT.set(_request_context(request))
        result = await run_in_threadpool(run_agent, str(stored_resume.local_path), config, trigger="manual", user_email=user_email)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if stored_resume.uri:
        result["resume_uri"] = stored_resume.uri
    if start_daily:
        if not daily_at:
            raise HTTPException(status_code=400, detail="Daily time is required when scheduling is enabled.")
        user_scheduler = schedulers.get_or_create(user_email)
        background_tasks.add_task(
            user_scheduler.start,
            str(stored_resume.local_path),
            config,
            daily_at,
            user_email,
            daily_timezone,
            stored_resume.uri,
        )
        result["scheduler"] = {"running": True, "daily_at": daily_at, "timezone": daily_timezone}
    return result


@app.post("/api/scheduler/start")
async def start_scheduler(
    resume: Annotated[UploadFile | None, File()] = None,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    linkedin_profile_url: Annotated[str, Form()] = "",
    naukri_profile_url: Annotated[str, Form()] = "",
    target_roles: Annotated[str, Form()] = "",
    locations: Annotated[str, Form()] = "",
    skills: Annotated[str, Form()] = "",
    experience_years: Annotated[str, Form()] = "",
    job_description: Annotated[str, Form()] = "",
    application_mode: Annotated[str, Form()] = "draft",
    max_jobs_per_portal: Annotated[int, Form()] = 10,
    daily_at: Annotated[str, Form()] = "",
    daily_timezone: Annotated[str, Form()] = "UTC",
    consent: Annotated[bool, Form()] = False,
) -> dict:
    user_email = require_user(job_agent_session)
    if not daily_at:
        raise HTTPException(status_code=400, detail="Daily time is required to schedule the agent.")
    _require_consent(user_email, consent)
    years = _require_profile_fields(name=name, phone=phone, target_roles=target_roles, locations=locations,
                                    skills=skills, experience_years=experience_years, max_jobs_per_portal=max_jobs_per_portal)
    enforce_limit("schedule", user_email)
    stored_resume = await resolve_resume(resume, user_email)
    config = _config_for_user(user_email, build_config_from_form(
        name=name,
        email=user_email,
        phone=phone,
        linkedin_profile_url=linkedin_profile_url,
        naukri_profile_url=naukri_profile_url,
        target_roles=target_roles,
        locations=locations,
        skills=skills,
        experience_years=years,
        job_description=job_description,
        application_mode=application_mode,
        max_jobs_per_portal=max_jobs_per_portal,
    ))
    _save_profile(user_email, config, stored_resume)
    scheduler = schedulers.get_or_create(user_email)
    scheduler.start(
        str(stored_resume.local_path),
        config,
        daily_at,
        user_email,
        timezone_name=daily_timezone,
        resume_uri=stored_resume.uri,
    )
    return {"status": "scheduled", "scheduler": scheduler.snapshot()}


@app.post("/api/scheduler/stop")
def stop_scheduler(job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> dict:
    user_email = require_user(job_agent_session)
    disable_schedule(user_email)
    if uses_eventbridge_scheduler():
        delete_user_schedule(user_email)
    return schedulers.stop(user_email)


PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()\-]{5,20}$")


def _require_profile_fields(
    *, name: str, phone: str, target_roles: str, locations: str, skills: str, experience_years: str, max_jobs_per_portal: int,
) -> float:
    """Server-side twin of the form's required fields (marked * in the UI).

    LinkedIn URL, Naukri URL and the job description stay optional. Returns
    the experience in years. The browser checks first; this stops scripted
    or stale clients from running with an incomplete profile.
    """
    missing = [label for label, value in (
        ("Name", name), ("Phone", phone), ("Target roles", target_roles), ("Locations", locations),
        ("Skills", skills), ("Experience (years)", experience_years),
    ) if not str(value or "").strip()]
    if missing:
        raise HTTPException(status_code=422, detail="Please fill in the required fields: " + ", ".join(missing) + ".")
    digits = re.sub(r"\D", "", phone)
    if not PHONE_PATTERN.match(phone.strip()) or not 7 <= len(digits) <= 15:
        raise HTTPException(status_code=422, detail="Enter a valid phone number (7 to 15 digits, for example +91 98765 43210).")
    try:
        years = float(experience_years)
    except ValueError:
        raise HTTPException(status_code=422, detail="Experience (years) must be a number from 0 to 50.") from None
    if not 0 <= years <= 50:
        raise HTTPException(status_code=422, detail="Experience (years) must be a number from 0 to 50.")
    if not 1 <= max_jobs_per_portal <= 50:
        raise HTTPException(status_code=422, detail="Max jobs per source must be from 1 to 50.")
    return years


def _require_consent(user_email: str, consent_given: bool) -> None:
    """DPDP: process a resume only after the user accepted the current privacy notice."""
    if not REQUIRE_CONSENT or privacy.has_consent(user_email):
        return
    if consent_given:
        privacy.give_consent(user_email)
        return
    raise HTTPException(status_code=403, detail="Please accept the privacy notice before uploading or processing your resume.")


def run_agent(resume_path: str, config: AppConfig, trigger: str = "manual", user_email: str = "") -> dict:
    started = time.monotonic()
    start_run_budget(user_email)
    agent = JobHuntingAgent(config)
    try:
        report, jobs, results, improved_resume = agent.run(resume_path, build_documents=not bool(user_email))
    except Exception as exc:
        metrics.emit("run_failed", user_email=user_email, trigger=trigger, error=type(exc).__name__,
                     duration_s=round(time.monotonic() - started, 2))
        raise
    application_summary = _application_summary(results)
    generated_at = datetime.now().isoformat(timespec="seconds")
    improved_resume = _publish_improved_resume(improved_resume, user_email or config.profile.email or "anonymous", generated_at)
    result = {
        "ats_report": asdict(report),
        "jobs": [asdict(job) for job in jobs],
        "applications": [_application_payload(result) for result in results],
        "application_summary": application_summary,
        "output_dir": str(Path(config.application.data_dir).resolve()),
        "generated_at": generated_at,
        "trigger": trigger,
        "timings": dict(agent.timings),
        "improved_resume": improved_resume,
        "_config_snapshot": {
            "profile": asdict(config.profile),
            "application": asdict(config.application),
        },
        "portal_submission_note": (
            "Portal applications are prepared as drafts or recruiter emails. "
            "Authenticated LinkedIn/Naukri submission remains adapter-gated because those portals can require login, CAPTCHA, OTP, and screening answers."
        ),
    }
    if not user_email:
        artifact_uris = mirror_artifacts(config.application.data_dir, config.profile.email or "anonymous", result["generated_at"])
        if artifact_uris:
            result["artifact_uris"] = artifact_uris
    if user_email:
        run_id = record_run(user_email, result)
        result["run_id"] = run_id
        saved_profile = user_profile(user_email) or {}
        queued = approvals.queue_applications(
            user_email, run_id, result["applications"],
            resume_path=resume_path, resume_uri=str(saved_profile.get("resume_uri") or ""),
        )
        result["approvals_queued"] = queued
        _submit_document_task(f"base:{run_id}", _prepare_base_document, user_email, run_id)
        metrics.run_completed(user_email, result, duration_s=time.monotonic() - started)
        return _client_run_payload(result, run_id)
    return result


def run_scheduled_user(user_email: str) -> dict:
    saved = schedule_for_user(user_email)
    if not saved or not saved.get("active"):
        return {"status": "skipped", "reason": "schedule_inactive"}
    resume_path = saved.get("resume_path") or ""
    if not Path(resume_path).exists() and saved.get("resume_uri"):
        resume_path = str(download_file(saved["resume_uri"], _user_upload_dir(user_email)))
    try:
        result = run_agent(
            resume_path,
            _config_from_payload(saved["config_payload"]),
            trigger="scheduled",
            user_email=user_email,
        )
    except Exception as exc:
        update_schedule_status(user_email, last_error=str(exc))
        raise
    hour, minute = _parse_hhmm(saved["daily_at"])
    next_run = _next_run_time(hour, minute, _timezone(saved.get("timezone") or "UTC"))
    update_schedule_status(
        user_email,
        next_run_at=next_run.isoformat(timespec="minutes"),
        last_run_at=result["generated_at"],
        last_error="",
        last_result=result,
    )
    return result


@app.get("/api/runs/{run_id}/resume-status")
def resume_status(
    run_id: int,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user_email = require_user(job_agent_session)
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    improved = (run.get("payload") or {}).get("improved_resume") or {}
    ready = {
        str(item.get("artifact_id")): {"status": "ready", "validation": item.get("validation", {}), "change_summary": item.get("change_summary", {})}
        for item in improved.get("tailored_resumes", []) if isinstance(item, dict)
    }
    ready.update(improved.get("tailored_statuses") or {})
    return {
        "base": {
            "status": improved.get("status", "preparing"),
            "validation": improved.get("validation", {}),
            "error": improved.get("error", ""),
        },
        "tailored": ready,
        "templates": _template_statuses(improved),
        "template": _run_template(run.get("payload") or {}),
        "preferred_template": _run_template(run.get("payload") or {}, for_tailored=True),
    }


@app.post("/api/runs/{run_id}/tailored-resumes/{artifact_id}/prepare")
def prepare_tailored_resume(
    run_id: int,
    artifact_id: str,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user_email = require_user(job_agent_session)
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    enforce_limit("tailored_resume", user_email)
    payload = run.get("payload") or {}
    job = next((item for item in payload.get("jobs", []) if item.get("tailored_resume_id") == artifact_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Tailored resume is not part of this run.")
    improved = payload.get("improved_resume") or {}
    if any(item.get("artifact_id") == artifact_id for item in improved.get("tailored_resumes", []) if isinstance(item, dict)):
        return {"status": "ready", "artifact_id": artifact_id}

    def mark_preparing(current: dict) -> dict:
        current_improved = dict(current.get("improved_resume") or {})
        statuses = dict(current_improved.get("tailored_statuses") or {})
        statuses[artifact_id] = {"status": "preparing"}
        current_improved["tailored_statuses"] = statuses
        current["improved_resume"] = current_improved
        return current

    mutate_run_payload(user_email, run_id, mark_preparing)
    _submit_document_task(f"tailored:{run_id}:{artifact_id}", _prepare_tailored_document, user_email, run_id, artifact_id)
    return {"status": "preparing", "artifact_id": artifact_id}


def _run_template(payload: dict, *, for_tailored: bool = False) -> str:
    """The run's ATS template: the user's choice for tailored resumes, else the agent's pick."""
    from .resume_templates import DEFAULT_TEMPLATE, is_template

    improved = payload.get("improved_resume") or {}
    candidates = (improved.get("preferred_template"), improved.get("template")) if for_tailored else (improved.get("template"),)
    return next((str(value) for value in candidates if is_template(value)), DEFAULT_TEMPLATE)


def _template_statuses(improved: dict) -> dict:
    """Status of every template for this run; the base resume counts as its template."""
    statuses: dict[str, dict] = {}
    base_template = improved.get("template")
    if base_template and improved.get("status") == "ready":
        validation = improved.get("validation") or {}
        statuses[str(base_template)] = {"status": "ready", "passed": bool(validation.get("passed")), "page_count": validation.get("page_count"), "base": True}
    for key, artifact in (improved.get("template_resumes") or {}).items():
        validation = (artifact or {}).get("validation") or {}
        statuses[key] = {"status": "ready", "passed": bool(validation.get("passed")), "page_count": validation.get("page_count")}
    for key, status in (improved.get("template_statuses") or {}).items():
        if status.get("status") != "ready" and key not in statuses:
            statuses[key] = status
    return statuses


def _template_artifact(improved: dict, template: str) -> dict | None:
    if improved.get("template") == template and improved.get("status") == "ready":
        return improved
    artifact = (improved.get("template_resumes") or {}).get(template)
    return artifact if isinstance(artifact, dict) else None


@app.get("/api/resume-templates")
def resume_templates(
    run_id: Annotated[int, Query()] = 0,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    """The ATS templates, with the agent's recommendation for this run or profile."""
    from .resume_templates import catalog, recommend_template

    user_email = require_user(job_agent_session)
    run = run_for_user(user_email, run_id) if run_id else None
    improved = ((run or {}).get("payload") or {}).get("improved_resume") or {}
    recommended, reason = improved.get("recommended_template"), improved.get("template_reason", "")
    if not recommended:
        profile = _profile_for_user(user_email)
        recommended, reason = recommend_template(float(profile.get("experience_years") or 0))
    return {
        "templates": catalog(str(recommended), str(reason)),
        "recommended": recommended,
        "statuses": _template_statuses(improved) if run else {},
        "preferred_template": _run_template((run or {}).get("payload") or {}, for_tailored=True) if run else recommended,
    }


@app.post("/api/runs/{run_id}/resume-templates/{template}/prepare")
def prepare_template_resume(
    run_id: int,
    template: str,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    from .resume_templates import is_template

    user_email = require_user(job_agent_session)
    template = template.strip().lower()
    if not is_template(template):
        raise HTTPException(status_code=404, detail="Unknown resume template.")
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    improved = (run.get("payload") or {}).get("improved_resume") or {}
    if _template_artifact(improved, template):
        return {"status": "ready", "template": template}
    enforce_limit("tailored_resume", user_email)

    def mark_preparing(current: dict) -> dict:
        current_improved = dict(current.get("improved_resume") or {})
        statuses = dict(current_improved.get("template_statuses") or {})
        statuses[template] = {"status": "preparing"}
        current_improved["template_statuses"] = statuses
        current["improved_resume"] = current_improved
        return current

    mutate_run_payload(user_email, run_id, mark_preparing)
    _submit_document_task(f"template:{run_id}:{template}", _prepare_template_document, user_email, run_id, template)
    return {"status": "preparing", "template": template}


@app.post("/api/runs/{run_id}/resume-template")
def choose_resume_template(
    run_id: int,
    payload: Annotated[dict, Body()],
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    """Use this template for the tailored resumes prepared from now on."""
    from .resume_templates import get_template, is_template

    user_email = require_user(job_agent_session)
    template = str(payload.get("template") or "").strip().lower()
    if not is_template(template):
        raise HTTPException(status_code=400, detail="Unknown resume template.")
    if not run_for_user(user_email, run_id):
        raise HTTPException(status_code=404, detail="Run not found.")

    def choose(current: dict) -> dict:
        improved = dict(current.get("improved_resume") or {})
        improved["preferred_template"] = template
        current["improved_resume"] = improved
        return current

    mutate_run_payload(user_email, run_id, choose)
    metrics.emit("resume_template_chosen", user_email=user_email, template=template)
    return {"preferred_template": template, "name": get_template(template).name}


@app.get("/api/runs/{run_id}/resume-templates/{template}/{file_format}")
def download_template_resume(
    run_id: int,
    template: str,
    file_format: str,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
):
    user_email = require_user(job_agent_session)
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    artifact = _template_artifact((run.get("payload") or {}).get("improved_resume") or {}, template.strip().lower())
    if not artifact:
        raise HTTPException(status_code=404, detail="Prepare this template first.")
    if file_format.casefold() == "preview":
        pages = ((artifact.get("validation") or {}).get("rendered_pages") or [])
        preview = Path(str(pages[0])) if pages else None
        if preview and preview.is_file():
            return FileResponse(preview, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
        raise HTTPException(status_code=404, detail="Preview is not available.")
    return _resume_file_response(artifact, file_format)


@app.get("/api/runs/{run_id}/improved-resume")
def download_improved_resume(
    run_id: int,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
):
    user_email = require_user(job_agent_session)
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    payload = run.get("payload") or {}
    improved = payload.get("improved_resume") or {}
    return _resume_file_response(improved, "docx")


@app.get("/api/runs/{run_id}/improved-resume.pdf")
def download_improved_resume_pdf(
    run_id: int,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
):
    user_email = require_user(job_agent_session)
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    improved = (run.get("payload") or {}).get("improved_resume") or {}
    return _resume_file_response(improved, "pdf")


@app.get("/api/runs/{run_id}/tailored-resumes/{artifact_id}/{file_format}")
def download_tailored_resume(
    run_id: int,
    artifact_id: str,
    file_format: str,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
):
    user_email = require_user(job_agent_session)
    run = run_for_user(user_email, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    improved = (run.get("payload") or {}).get("improved_resume") or {}
    artifact = next(
        (
            item
            for item in improved.get("tailored_resumes", [])
            if isinstance(item, dict) and str(item.get("artifact_id")) == artifact_id
        ),
        None,
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Tailored resume artifact is not available for this run.")
    return _resume_file_response(artifact, file_format)


def _resume_file_response(artifact: dict, file_format: str):
    normalized_format = file_format.casefold()
    if normalized_format not in {"docx", "pdf"}:
        raise HTTPException(status_code=400, detail="Resume format must be docx or pdf.")
    uri = str(artifact.get(f"{normalized_format}_uri") or "")
    if uri:
        signed_url = presigned_download_url(uri)
        if signed_url:
            return RedirectResponse(signed_url, status_code=303)
    path = Path(str(artifact.get(f"{normalized_format}_path") or ""))
    if path.exists() and path.is_file():
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if normalized_format == "docx"
            else "application/pdf"
        )
        return FileResponse(path, media_type=media_type, filename=path.name)
    raise HTTPException(status_code=404, detail="Resume artifact is not available for this run.")


def _submit_document_task(key: str, function, *args) -> bool:
    with _document_tasks_lock:
        if key in _document_tasks:
            return False
        _document_tasks.add(key)
    future = DOCUMENT_EXECUTOR.submit(function, *args)
    future.add_done_callback(lambda _: _finish_document_task(key))
    return True


def _finish_document_task(key: str) -> None:
    with _document_tasks_lock:
        _document_tasks.discard(key)


def _prepare_base_document(user_email: str, run_id: int) -> None:
    try:
        run = run_for_user(user_email, run_id)
        if not run:
            return
        payload = run.get("payload") or {}
        resume, report, config, resume_hash = _document_inputs(payload)
        template = _run_template(payload)
        key = document_cache_key(resume_hash, config.profile, config.application.resume_page_target, template=template)
        artifact, _ = cached_document(
            config.application.data_dir,
            key,
            lambda output: write_base_resume(
                resume, report, config.profile, output,
                page_target=config.application.resume_page_target, template=template,
            ),
        )
        artifact = _publish_document_artifact(
            artifact, user_email, str(payload.get("generated_at") or run_id), "base"
        )

        def complete(current: dict) -> dict:
            previous = current.get("improved_resume") or {}
            current["improved_resume"] = {
                **previous, **artifact, "artifact_id": "base", "status": "ready",
                "tailored_resumes": previous.get("tailored_resumes", []),
            }
            return current

        mutate_run_payload(user_email, run_id, complete)
        _emit_document_ready(user_email, "base", artifact)
    except Exception as exc:
        _mark_document_failure(user_email, run_id, "base", str(exc))


def _prepare_template_document(user_email: str, run_id: int, template: str) -> None:
    """The run's ATS resume in another template, with the same checks as the base resume."""
    try:
        run = run_for_user(user_email, run_id)
        if not run:
            return
        payload = run.get("payload") or {}
        resume, report, config, resume_hash = _document_inputs(payload)
        key = document_cache_key(resume_hash, config.profile, config.application.resume_page_target, template=template)
        artifact, _ = cached_document(
            config.application.data_dir,
            key,
            lambda output: write_base_resume(
                resume, report, config.profile, output,
                page_target=config.application.resume_page_target, template=template,
            ),
        )
        artifact = _publish_document_artifact(
            artifact, user_email, str(payload.get("generated_at") or run_id), f"templates/{template}"
        )

        def complete(current: dict) -> dict:
            improved = dict(current.get("improved_resume") or {})
            artifacts = dict(improved.get("template_resumes") or {})
            artifacts[template] = artifact
            statuses = dict(improved.get("template_statuses") or {})
            statuses[template] = {"status": "ready"}
            improved.update({"template_resumes": artifacts, "template_statuses": statuses})
            current["improved_resume"] = improved
            return current

        mutate_run_payload(user_email, run_id, complete)
        _emit_document_ready(user_email, "template", artifact)
    except Exception as exc:
        _mark_document_failure(user_email, run_id, f"template:{template}", str(exc))


def _prepare_tailored_document(user_email: str, run_id: int, artifact_id: str) -> None:
    try:
        run = run_for_user(user_email, run_id)
        if not run:
            return
        payload = run.get("payload") or {}
        resume, report, config, resume_hash = _document_inputs(payload)
        job_payload = next(item for item in payload.get("jobs", []) if item.get("tailored_resume_id") == artifact_id)
        job = _job_from_payload(job_payload)
        template = _run_template(payload, for_tailored=True)
        key = document_cache_key(resume_hash, config.profile, config.application.resume_page_target, job, template=template)
        artifact, _ = cached_document(
            config.application.data_dir,
            key,
            lambda output: write_tailored_resume(
                resume, report, config.profile, output, job,
                page_target=config.application.resume_page_target, template=template,
            ),
        )
        artifact = _publish_document_artifact(
            artifact, user_email, str(payload.get("generated_at") or run_id), f"tailored/{artifact_id}"
        )
        # What changed, with the resume line that supports every added skill.
        artifact["change_summary"] = change_summary(resume, job, artifact)

        def complete(current: dict) -> dict:
            improved = dict(current.get("improved_resume") or {})
            artifacts = [item for item in improved.get("tailored_resumes", []) if item.get("artifact_id") != artifact_id]
            artifacts.append(artifact)
            statuses = dict(improved.get("tailored_statuses") or {})
            statuses[artifact_id] = {"status": "ready", "validation": artifact.get("validation", {}), "change_summary": artifact.get("change_summary", {})}
            improved.update({"tailored_resumes": artifacts, "tailored_statuses": statuses})
            current["improved_resume"] = improved
            return current

        mutate_run_payload(user_email, run_id, complete)
        _emit_document_ready(user_email, "tailored", artifact)
    except Exception as exc:
        _mark_document_failure(user_email, run_id, artifact_id, str(exc))


def _emit_document_ready(user_email: str, kind: str, artifact: dict) -> None:
    validation = artifact.get("validation") or {}
    facts = validation.get("factual_consistency") or {}
    metrics.emit(
        "resume_ready", user_email=user_email, kind=kind, passed=bool(validation.get("passed")),
        page_count=validation.get("page_count"), page_target_met=bool(validation.get("page_target_met")),
        factual_passed=bool(facts.get("passed", True)),
    )


def _mark_document_failure(user_email: str, run_id: int, artifact_id: str, detail: str) -> None:
    kind = "base" if artifact_id == "base" else "template" if artifact_id.startswith("template:") else "tailored"
    metrics.emit("resume_failed", user_email=user_email, kind=kind, factual="validation failed" in detail.casefold())
    def fail(current: dict) -> dict:
        improved = dict(current.get("improved_resume") or {})
        message = re.sub(r"\s+", " ", detail).strip()[:300]
        if artifact_id == "base":
            improved.update({"status": "failed", "error": message})
        elif kind == "template":
            statuses = dict(improved.get("template_statuses") or {})
            statuses[artifact_id.removeprefix("template:")] = {"status": "failed", "error": message}
            improved["template_statuses"] = statuses
        else:
            statuses = dict(improved.get("tailored_statuses") or {})
            statuses[artifact_id] = {"status": "failed", "error": message}
            improved["tailored_statuses"] = statuses
        current["improved_resume"] = improved
        return current

    mutate_run_payload(user_email, run_id, fail)


def _publish_document_artifact(artifact: dict[str, object], user_email: str, generated_at: str, suffix: str) -> dict[str, object]:
    published = dict(artifact)
    prefix = f"artifacts/{normalize_email(user_email)}/{generated_at}/improved_resume/{suffix}"
    for file_format in ("docx", "pdf"):
        path = artifact.get(f"{file_format}_path")
        if path:
            published[f"{file_format}_uri"] = upload_file(str(path), prefix)
    return published


def _document_inputs(payload: dict) -> tuple[Resume, AtsReport, AppConfig, str]:
    improved = payload.get("improved_resume") or {}
    source = improved.get("_resume_snapshot") or {}
    resume = Resume(
        str(source.get("path", "")), str(source.get("text", "")),
        tuple(source.get("inferred_skills", ())), tuple(source.get("inferred_roles", ())),
        dict(source.get("sections", {})),
    )
    report_data = dict(payload.get("ats_report") or {})
    for field in ("strengths", "improvements", "missing_keywords", "detected_sections", "matched_keywords"):
        report_data[field] = tuple(report_data.get(field, ()))
    report_data["score_breakdown"] = tuple(tuple(item) for item in report_data.get("score_breakdown", ()))
    report_data["score_range"] = tuple(report_data.get("score_range", (0, 100)))
    config = _config_from_snapshot(payload.get("_config_snapshot") or {})
    return resume, AtsReport(**report_data), config, str(improved.get("_resume_hash") or "")


def _config_from_snapshot(source: dict) -> AppConfig:
    profile = dict(source.get("profile") or {})
    search = dict(source.get("search") or {})
    application = dict(source.get("application") or {})
    email = dict(source.get("email") or {})
    for field in ("target_roles", "locations", "skills"):
        profile[field] = tuple(profile.get(field, ()))
    search["portals"] = tuple(search.get("portals", DEFAULT_PORTALS))
    return AppConfig(CandidateProfile(**profile), SearchConfig(**search), ApplicationConfig(**application), EmailConfig(**email))


def _job_from_payload(source: dict) -> JobLead:
    values = dict(source)
    values["match_reasons"] = tuple(values.get("match_reasons", ()))
    values["additional_skills"] = tuple(values.get("additional_skills", ()))
    return JobLead(**values)


def _publish_improved_resume(improved_resume: dict[str, object], user_email: str, generated_at: str) -> dict[str, object]:
    published = dict(improved_resume)
    prefix = f"artifacts/{normalize_email(user_email)}/{generated_at}/improved_resume"
    for file_format in ("docx", "pdf"):
        file_path = improved_resume.get(f"{file_format}_path")
        if file_path:
            published[f"{file_format}_uri"] = upload_file(str(file_path), prefix)
    tailored: list[dict[str, object]] = []
    for artifact in improved_resume.get("tailored_resumes", []):
        if not isinstance(artifact, dict):
            continue
        item = dict(artifact)
        artifact_prefix = f"{prefix}/tailored/{item.get('artifact_id', 'resume')}"
        for file_format in ("docx", "pdf"):
            file_path = item.get(f"{file_format}_path")
            if file_path:
                item[f"{file_format}_uri"] = upload_file(str(file_path), artifact_prefix)
        tailored.append(item)
    published["tailored_resumes"] = tailored
    return published


def _application_payload(result) -> dict:
    payload = asdict(result)
    draft_path = _draft_path_from_detail(result.status, result.detail)
    if draft_path:
        payload["draft_path"] = str(draft_path)
        payload["draft_message"] = _read_draft_message(draft_path)
    return payload


def _draft_path_from_detail(status: str, detail: str) -> Path | None:
    if status == "drafted":
        return Path(detail)
    if "Draft saved to " in detail:
        return Path(detail.rsplit("Draft saved to ", 1)[1])
    return None


def _read_draft_message(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return ""


def _application_summary(results) -> dict[str, int]:
    summary = {"drafted": 0, "pending_approval": 0, "emailed": 0, "email_failed": 0, "skipped": 0}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    return summary


def _history_item(trigger: str, started_at: str, result: dict) -> dict:
    return {
        "trigger": trigger,
        "started_at": started_at,
        "finished_at": result["generated_at"],
        "status": "completed",
        "ats_score": result["ats_report"]["score"],
        "jobs": len(result["jobs"]),
        "applications": result["application_summary"],
    }


async def save_resume_upload(resume: UploadFile, user_email: str = "anonymous") -> StoredObject:
    suffix = Path(resume.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md"}:
        raise HTTPException(status_code=400, detail="Upload a PDF, DOCX, TXT, or MD resume.")
    upload_dir = _user_upload_dir(user_email)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{Path(resume.filename or 'resume').name}"
    with target.open("wb") as handle:
        shutil.copyfileobj(resume.file, handle)
    uri = upload_file(target, f"uploads/{normalize_email(user_email)}/{target.stem}")
    return StoredObject(local_path=target, uri=uri)


async def resolve_resume(resume: UploadFile | None, user_email: str) -> StoredObject:
    if resume and resume.filename:
        return await save_resume_upload(resume, user_email)
    saved_profile = user_profile(user_email)
    saved_schedule = schedule_for_user(user_email)
    resume_path = (saved_profile or {}).get("resume_path") or (saved_schedule or {}).get("resume_path") or ""
    resume_uri = (saved_profile or {}).get("resume_uri") or (saved_schedule or {}).get("resume_uri") or ""
    path = Path(resume_path) if resume_path else Path()
    if resume_path and path.exists():
        return StoredObject(local_path=path, uri=resume_uri)
    if resume_uri:
        return StoredObject(local_path=download_file(resume_uri, _user_upload_dir(user_email)), uri=resume_uri)
    raise HTTPException(status_code=400, detail="Upload a resume before running or scheduling the agent.")


def _config_for_user(user_email: str, config: AppConfig) -> AppConfig:
    return replace(
        config,
        application=replace(config.application, data_dir=str(_user_data_dir(user_email))),
    )


def _user_data_dir(user_email: str) -> Path:
    user_key = hashlib.sha256(normalize_email(user_email).encode("utf-8")).hexdigest()[:20]
    return DATA_DIR / "users" / user_key


def _user_upload_dir(user_email: str) -> Path:
    return _user_data_dir(user_email) / "uploads"


def _save_profile(user_email: str, config: AppConfig, resume: StoredObject) -> None:
    save_user_profile(
        user_email,
        _config_payload(config),
        resume_path=str(resume.local_path),
        resume_uri=resume.uri,
        resume_name=resume.local_path.name,
    )


def _profile_for_user(user_email: str) -> dict:
    saved = user_profile(user_email)
    scheduled = schedule_for_user(user_email)
    if saved:
        payload = saved.get("profile_payload") or {}
        view = _profile_view(payload, saved)
        view["daily_at"] = (scheduled or {}).get("daily_at") or ""
        return view
    if scheduled:
        view = _profile_view(
            scheduled.get("config_payload") or {},
            {
                "resume_path": scheduled.get("resume_path") or "",
                "resume_uri": scheduled.get("resume_uri") or "",
                "resume_name": Path(scheduled.get("resume_path") or "").name,
            },
        )
        view["daily_at"] = scheduled.get("daily_at") or ""
        return view
    return {
        "name": "",
        "email": normalize_email(user_email),
        "phone": "",
        "linkedin_profile_url": "",
        "naukri_profile_url": "",
        "target_roles": "",
        "locations": "",
        "skills": "",
        "experience_years": 0,
        "job_description": "",
        "max_jobs_per_portal": 10,
        "application_mode": "draft",
        "daily_at": "",
        "resume_name": "",
        "resume_uri": "",
    }


def _profile_view(payload: dict, stored: dict) -> dict:
    profile = payload.get("profile") or {}
    search = payload.get("search") or {}
    application = payload.get("application") or {}
    return {
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin_profile_url": profile.get("linkedin_profile_url", ""),
        "naukri_profile_url": profile.get("naukri_profile_url", ""),
        "target_roles": ", ".join(profile.get("target_roles") or ()),
        "locations": ", ".join(profile.get("locations") or ()),
        "skills": ", ".join(profile.get("skills") or ()),
        "experience_years": max(0.0, float(profile.get("experience_years", 0) or 0)),
        "job_description": str(profile.get("job_description", "") or ""),
        "max_jobs_per_portal": int(search.get("max_jobs_per_portal", 10)),
        "application_mode": application.get("mode", "draft"),
        "resume_name": stored.get("resume_name") or Path(stored.get("resume_path") or "").name,
        "resume_uri": stored.get("resume_uri") or "",
    }


def _persisted_scheduler_snapshot(user_email: str) -> dict:
    saved = schedule_for_user(user_email)
    if not saved:
        return _empty_scheduler_snapshot()
    return {
        "running": bool(saved.get("active")),
        "daily_at": saved.get("daily_at"),
        "timezone": saved.get("timezone") or "UTC",
        "next_run_at": saved.get("next_run_at"),
        "created_at": saved.get("created_at"),
        "last_run_at": saved.get("last_run_at"),
        "last_error": saved.get("last_error"),
        "resume_path": saved.get("resume_path"),
        "last_result": saved.get("last_result"),
        "history": [],
    }


def _run_history_item(run: dict) -> dict:
    payload = run.get("payload") or {}
    return {
        "trigger": run.get("trigger") or payload.get("trigger") or "manual",
        "finished_at": run.get("generated_at") or payload.get("generated_at") or "",
        "status": "completed",
        "ats_score": run.get("ats_score", 0),
        "jobs": run.get("job_count", 0),
        "applications": run.get("application_summary") or {},
    }


def _run_with_payload_id(run: dict) -> dict:
    payload = dict(run.get("payload") or {})
    run_id = int(run.get("id") or payload.get("run_id") or 0)
    payload["run_id"] = run_id
    return {**run, "payload": _client_run_payload(payload, run_id)}


def _client_run_payload(payload: dict, run_id: int) -> dict:
    client_payload = dict(payload)
    client_payload.pop("_config_snapshot", None)
    page = paginate_jobs(
        list(payload.get("jobs") or []),
        run_id=run_id,
        secret=APP_SECRET,
        limit=DEFAULT_JOB_PAGE_SIZE,
    )
    client_payload["run_id"] = run_id
    client_payload["jobs"] = page["jobs"]
    client_payload["job_page"] = page["page"]
    client_payload["job_count"] = page["page"]["total"]
    applications = list(payload.get("applications") or [])
    client_payload["applications"] = applications[:1]
    client_payload["application_count"] = len(applications)
    improved = dict(client_payload.get("improved_resume") or {})
    improved.pop("tailored_resumes", None)
    improved.pop("template_resumes", None)
    improved["template_statuses"] = _template_statuses(dict(client_payload.get("improved_resume") or {}))
    improved.pop("_resume_snapshot", None)
    improved.pop("_resume_hash", None)
    client_payload["improved_resume"] = improved
    return client_payload


def _mock_test_candidate_jobs(user_email: str, run_limit: int = 3) -> list[tuple[int, dict]]:
    """Jobs from the user's recent runs, newest first and de-duplicated."""
    seen: set[str] = set()
    jobs: list[tuple[int, dict]] = []
    for run in latest_runs(user_email, limit=run_limit):
        run_id = int(run.get("payload_run_id") or run.get("id") or 0)
        for job in (run.get("payload") or {}).get("jobs") or []:
            if not isinstance(job, dict) or not job.get("title"):
                continue
            stable_id = _mock_test_job_id(job)
            if stable_id in seen:
                continue
            seen.add(stable_id)
            jobs.append((run_id, job))
            if len(jobs) >= 60:
                return jobs
    return jobs


def _mock_test_job_id(job: dict) -> str:
    return f"{job.get('portal') or ''}:{job.get('source_id') or job.get('url') or ''}".lower()


def _mock_test_job(user_email: str, job_id: str, run_id: int | None) -> dict | None:
    if not job_id:
        return None
    if run_id:
        run = run_for_user(user_email, int(run_id))
        for job in ((run or {}).get("payload") or {}).get("jobs") or []:
            if isinstance(job, dict) and _mock_test_job_id(job) == job_id:
                return job
    return next((job for _, job in _mock_test_candidate_jobs(user_email) if _mock_test_job_id(job) == job_id), None)


def _mock_test_job_summary(job: dict, run_id: int) -> dict:
    metadata = job.get("source_metadata") or {}
    return {
        "job_id": _mock_test_job_id(job),
        "run_id": run_id,
        "title": job.get("title") or "",
        "company": job.get("company") or "",
        "location": job.get("location") or "",
        "portal": job.get("portal") or "",
        "match_score": job.get("match_score") or 0,
        "skills": list(dict.fromkeys([
            *list(metadata.get("matched_skills") or ()),
            *list(job.get("additional_skills") or ()),
            *list(metadata.get("missing_required_skills") or ()),
        ]))[:10],
    }


def _mock_test_client_payload(record: dict) -> dict:
    """Shape a stored test for the browser; the key is included only after grading."""
    completed = record.get("status") == "completed"
    payload = {
        "test_id": record.get("id"),
        "status": record.get("status"),
        "job_id": record.get("job_id") or "",
        "run_id": record.get("run_id"),
        "job_title": record.get("job_title") or "General practice",
        "company": record.get("company") or "",
        "length": record.get("length"),
        "difficulty": record.get("difficulty"),
        "topics": record.get("topics") or [],
        "time_limit_seconds": int(record.get("time_limit_seconds") or 0),
        "started_at": record.get("started_at"),
        "completed_at": record.get("completed_at"),
        "questions": public_questions(record.get("questions") or []),
        "difficulty_mix": {
            name: sum(1 for item in record.get("questions") or [] if item.get("difficulty") == name) for name in ("easy", "medium", "hard")
        },
        "coding_count": sum(1 for item in record.get("questions") or [] if item.get("kind") == "code"),
    }
    if completed:
        payload["scorecard"] = record.get("scorecard") or {}
    else:
        started = _parse_iso_time(record.get("started_at"))
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() if started else 0
        payload["remaining_seconds"] = max(0, int(payload["time_limit_seconds"] - elapsed))
    return payload


def _mock_test_history_item(record: dict) -> dict:
    scorecard = record.get("scorecard") or {}
    return {
        "test_id": record.get("id"),
        "job_title": record.get("job_title") or "General practice",
        "company": record.get("company") or "",
        "length": record.get("length"),
        "difficulty": record.get("difficulty"),
        "score": record.get("score"),
        "total": record.get("total"),
        "percent": record.get("percent"),
        "grade": scorecard.get("grade", ""),
        "readiness": (scorecard.get("readiness") or {}).get("label", ""),
        "completed_at": record.get("completed_at"),
    }


def _request_context(request: Request) -> RequestContext:
    """End-user IP/User-Agent; behind CloudFront/ALB the first forwarded hop."""
    forwarded = request.headers.get("x-forwarded-for", "")
    user_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
    return RequestContext(user_ip=user_ip[:64], user_agent=request.headers.get("user-agent", "")[:300])


def _parse_iso_time(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _mock_interview_payload(profile: dict, latest_payload: dict | None = None) -> dict:
    latest_payload = latest_payload or {}
    roles = _split_csv(profile.get("target_roles", ""))
    skills = _split_csv(profile.get("skills", ""))
    if latest_payload.get("ats_report"):
        skills = _ordered_unique((*skills, *tuple(latest_payload.get("ats_report", {}).get("missing_keywords") or ())))
    roles = roles or tuple(latest_payload.get("ats_report", {}).get("target_roles") or ()) or ("Data Engineer",)
    skills = skills or ("Python", "SQL", "Spark", "AWS")
    level = interview_level(float(profile.get("experience_years") or 0), roles[0] if roles else "")
    questions = _mock_interview_questions_for(roles, skills, level)
    return {
        "roles": roles,
        "skills": skills,
        "level": level,
        "experience_years": float(profile.get("experience_years") or 0),
        "question_count": sum(len(group["questions"]) for group in questions),
        "groups": questions,
        "coding_slots": CODING_SLOTS if is_technical_interview(roles, skills) else {mode: 0 for mode in CODING_SLOTS},
    }


def _job_interview_payload(job: dict, base: dict) -> dict:
    """Point the interview at one job lead: its title, skills and posting."""
    focus = job_interview_focus(job)
    roles = (focus["title"],)
    skills = tuple(_ordered_unique((*focus["skills"], *focus["gaps"]))) or tuple(base.get("skills") or ())
    required = job.get("required_experience")
    years = float(required) if isinstance(required, (int, float)) else float(base.get("experience_years") or 0)
    level = interview_level(years, focus["title"])
    groups = _mock_interview_questions_for(roles, skills, level)
    job_fit_group = build_job_fit_group(focus)
    return {
        "roles": roles,
        "skills": skills,
        "level": level,
        "experience_years": years,
        "coding_slots": CODING_SLOTS if is_technical_interview(roles, skills) else {mode: 0 for mode in CODING_SLOTS},
        "question_count": sum(len(group["questions"]) for group in groups) + len(job_fit_group["questions"]),
        "groups": groups,
        "job_fit_group": job_fit_group,
        "job": {
            "job_id": _mock_test_job_id(job),
            "title": focus["title"],
            "company": focus["company"],
            "location": focus["location"],
            "skills": list(focus["skills"]),
            "gaps": list(focus["gaps"]),
            "responsibilities": list(focus["responsibilities"]),
            "has_description": focus["has_description"],
        },
    }


def _mock_interview_questions_for(roles: tuple[str, ...], skills: tuple[str, ...], level: str = "mid") -> list[dict]:
    return build_question_groups(roles, skills, level)


def _interview_mode_for_limit(limit: int) -> str:
    if limit <= 5:
        return "quick"
    if limit >= 10:
        return "deep"
    return "standard"


def _interview_question_sequence(
    groups: list[dict],
    limit: int,
    mode: str = "standard",
    *,
    previous_questions: tuple[dict | str, ...] | list[dict | str] = (),
    seed: str | None = None,
) -> list[dict]:
    return select_question_sequence(
        groups,
        limit,
        mode,
        previous_questions=previous_questions,
        seed=seed,
    )


def _accent_for_region(region: str) -> dict:
    normalized = region.strip().lower()
    accents = {
        "india": {"label": "Indian English", "lang": "en-IN", "azure_voice": "en-IN-NeerjaNeural", "female_voice_hints": ["Heera", "Veena", "Aditi", "Raveena", "Neerja", "Kavya", "Swara"], "male_voice_hints": ["Ravi", "Prabhat", "Kunal"]},
        "united states": {"label": "US English", "lang": "en-US", "azure_voice": "en-US-JennyNeural", "female_voice_hints": ["Zira", "Jenny", "Aria", "Samantha", "Ava", "Joanna", "Salli"], "male_voice_hints": ["David", "Mark", "Guy", "Christopher", "Eric"]},
        "usa": {"label": "US English", "lang": "en-US", "azure_voice": "en-US-JennyNeural", "female_voice_hints": ["Zira", "Jenny", "Aria", "Samantha", "Ava", "Joanna", "Salli"], "male_voice_hints": ["David", "Mark", "Guy", "Christopher", "Eric"]},
        "united kingdom": {"label": "British English", "lang": "en-GB", "azure_voice": "en-GB-SoniaNeural", "female_voice_hints": ["Hazel", "Sonia", "Libby", "Susan", "Amy", "Emma"], "male_voice_hints": ["George", "Ryan", "Arthur", "Brian"]},
        "uk": {"label": "British English", "lang": "en-GB", "azure_voice": "en-GB-SoniaNeural", "female_voice_hints": ["Hazel", "Sonia", "Libby", "Susan", "Amy", "Emma"], "male_voice_hints": ["George", "Ryan", "Arthur", "Brian"]},
        "australia": {"label": "Australian English", "lang": "en-AU", "azure_voice": "en-AU-NatashaNeural", "female_voice_hints": ["Karen", "Catherine", "Olivia", "Nicole", "Natasha"], "male_voice_hints": ["Lee", "William", "Darren"]},
        "canada": {"label": "Canadian English", "lang": "en-CA", "azure_voice": "en-CA-ClaraNeural", "female_voice_hints": ["Clara", "Linda"], "male_voice_hints": ["Liam"]},
        "singapore": {"label": "Singapore English", "lang": "en-SG", "azure_voice": "en-SG-LunaNeural", "female_voice_hints": ["Luna", "Seraphina", "Jia"], "male_voice_hints": ["Wayne"]},
    }
    if normalized not in accents:
        raise HTTPException(status_code=400, detail="Choose India, United States, United Kingdom, Australia, Canada, or Singapore.")
    return {**accents[normalized], "interviewer": "Sarah", "gender": "Female"}


@app.get("/api/mock-interview/accents")
def interviewer_accents(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    require_user(job_agent_session)
    countries = ("India", "United States", "United Kingdom", "Australia", "Canada", "Singapore")
    return {
        "accents": [{"region": country, **_accent_for_region(country)} for country in countries],
        "tts_provider": "azure" if AZURE_SPEECH_KEY and AZURE_SPEECH_REGION else "browser",
        "preview_text": "Hello, I'm Sarah, your interviewer. Tell me about a project you are proud of and the impact of your work.",
    }


@app.post("/api/mock-interview/speech/preview")
def preview_interviewer_accent(
    payload: Annotated[dict, Body()],
    job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    require_user(job_agent_session)
    voice = _accent_for_region(str(payload.get("region") or "India"))
    if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
        raise HTTPException(status_code=503, detail="Regional neural speech requires Azure Speech configuration.")
    try:
        audio = _azure_speech_audio(
            "Hello, I'm Sarah, your interviewer. Tell me about a project you are proud of and the impact of your work.", voice
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="This regional voice is temporarily unavailable. Please retry.") from exc
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/mock-interview/speech")
def mock_interview_speech(
    payload: Annotated[dict, Body()],
    job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    user_email = require_user(job_agent_session)
    enforce_limit("speech", user_email)
    if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
        raise HTTPException(status_code=503, detail="Azure neural speech is not configured.")
    session_id = int(payload.get("session_id") or 0)
    question_id = str(payload.get("question_id") or "")
    session = mock_interview_session(user_email, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    question = next((item for item in session.get("questions") or [] if str(item.get("id") or "") == question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail="Interview question not found.")
    voice = _accent_for_region(str(session.get("region") or "India"))
    try:
        audio = _azure_speech_audio(str(question.get("question") or ""), voice)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Neural interviewer voice is temporarily unavailable.") from exc
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=300"})


def _azure_speech_audio(text: str, voice: dict) -> bytes:
    endpoint = f"https://{AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
    language = str(voice.get("lang") or "en-US")
    voice_name = str(voice.get("azure_voice") or "en-US-JennyNeural")
    ssml = (
        f"<speak version='1.0' xml:lang='{language}'>"
        f"<voice xml:lang='{language}' xml:gender='Female' name='{voice_name}'>"
        f"{xml_escape(text[:1200])}</voice></speak>"
    )
    response = requests.post(
        endpoint,
        headers={
            "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "job-hunting-agent",
        },
        data=ssml.encode("utf-8"),
        timeout=20,
    )
    response.raise_for_status()
    return response.content


def _score_mock_interview(
    answers: list[dict],
    questions: list[dict],
    *,
    roles: tuple[str, ...] = (),
    skills: tuple[str, ...] = (),
    interview_mode: str = "",
) -> dict:
    return evaluate_interview(
        answers,
        questions,
        roles=roles,
        skills=skills,
        interview_mode=interview_mode,
    )


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)


def build_config_from_form(
    *,
    name: str,
    email: str,
    phone: str,
    linkedin_profile_url: str,
    naukri_profile_url: str,
    target_roles: str,
    locations: str,
    skills: str,
    application_mode: str,
    max_jobs_per_portal: int,
    experience_years: float = 0,
    job_description: str = "",
) -> AppConfig:
    if application_mode not in {"draft", "email"}:
        raise HTTPException(status_code=400, detail="application_mode must be draft or email.")
    return AppConfig(
        profile=CandidateProfile(
            name=name.strip(),
            email=email.strip(),
            phone=phone.strip(),
            linkedin_profile_url=_profile_link(linkedin_profile_url, "linkedin.com", "LinkedIn"),
            naukri_profile_url=_profile_link(naukri_profile_url, "naukri.com", "Naukri"),
            target_roles=_split_csv(target_roles),
            locations=_split_csv(locations),
            skills=_split_csv(skills),
            experience_years=max(0.0, min(float(experience_years or 0), 50.0)),
            job_description=job_description.strip(),
        ),
        search=SearchConfig(max_jobs_per_portal=max(1, min(max_jobs_per_portal, 50))),
        application=ApplicationConfig(mode=application_mode, data_dir=str(DATA_DIR)),
        email=EmailConfig(
            smtp_host=os.getenv("JOB_AGENT_SMTP_HOST", ""),
            smtp_port=int(os.getenv("JOB_AGENT_SMTP_PORT", "587")),
            username=os.getenv("JOB_AGENT_SMTP_USERNAME", ""),
            password=os.getenv("JOB_AGENT_SMTP_PASSWORD", ""),
            from_email=os.getenv("JOB_AGENT_SMTP_FROM", email.strip()),
        ),
    )


def _profile_link(value: str, domain: str, label: str) -> str:
    """Normalise an optional profile link; reject anything off the portal's domain.

    These links are written into recruiter emails, so a typo or an unrelated
    URL would go out with every application.
    """
    cleaned = value.strip()
    if not cleaned:
        return ""
    if not re.match(r"^https?://", cleaned, re.I):
        cleaned = "https://" + cleaned.lstrip("/")
    try:
        parts = urlsplit(cleaned)
    except ValueError:
        parts = None
    host = (parts.hostname or "").casefold() if parts else ""
    if not parts or parts.scheme.casefold() not in {"http", "https"} or not (host == domain or host.endswith("." + domain)):
        raise HTTPException(status_code=400, detail=f"{label} profile URL must be a {domain} link, for example https://www.{domain}/...")
    return cleaned


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Daily time must be in HH:MM format.") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise HTTPException(status_code=400, detail="Daily time must be a valid 24-hour time.")
    return hour, minute


def _next_run_time(hour: int, minute: int, zone: ZoneInfo | None = None) -> datetime:
    zone = zone or _timezone("UTC")
    now = datetime.now(zone)
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def _timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _config_payload(config: AppConfig) -> dict:
    return {
        "profile": asdict(config.profile),
        "search": asdict(config.search),
        "application": asdict(config.application),
        "email": {
            "smtp_host": config.email.smtp_host,
            "smtp_port": config.email.smtp_port,
            "username": config.email.username,
            "from_email": config.email.from_email,
        },
    }


def _config_from_payload(payload: dict) -> AppConfig:
    profile = payload.get("profile", {})
    search = payload.get("search", {})
    application = payload.get("application", {})
    return AppConfig(
        profile=CandidateProfile(
            name=profile.get("name", ""),
            email=profile.get("email", ""),
            phone=profile.get("phone", ""),
            linkedin_profile_url=profile.get("linkedin_profile_url", ""),
            naukri_profile_url=profile.get("naukri_profile_url", ""),
            target_roles=tuple(profile.get("target_roles", ())),
            locations=tuple(profile.get("locations", ())),
            skills=tuple(profile.get("skills", ())),
            experience_years=max(0.0, float(profile.get("experience_years", 0) or 0)),
            job_description=str(profile.get("job_description", "") or ""),
        ),
        search=SearchConfig(
            max_jobs_per_portal=int(search.get("max_jobs_per_portal", 10)),
            freshness_days=int(search.get("freshness_days", 14)),
            include_remote=bool(search.get("include_remote", True)),
            validate_job_links=bool(search.get("validate_job_links", True)),
            # Saved schedules keep their portals, plus any source added since they were saved.
            portals=tuple(dict.fromkeys((*tuple(search.get("portals") or ()), *DEFAULT_PORTALS))),
        ),
        application=ApplicationConfig(
            mode=application.get("mode", "draft"),
            cover_letter_tone=application.get("cover_letter_tone", "concise"),
            data_dir=application.get("data_dir", str(DATA_DIR)),
            resume_page_target=max(1, min(int(application.get("resume_page_target", 2)), 3)),
            tailor_each_job=bool(application.get("tailor_each_job", True)),
        ),
        email=EmailConfig(
            smtp_host=os.getenv("JOB_AGENT_SMTP_HOST", ""),
            smtp_port=int(os.getenv("JOB_AGENT_SMTP_PORT", "587")),
            username=os.getenv("JOB_AGENT_SMTP_USERNAME", ""),
            password=os.getenv("JOB_AGENT_SMTP_PASSWORD", ""),
            from_email=os.getenv("JOB_AGENT_SMTP_FROM", profile.get("email", "")),
        ),
    )


def _escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


_AUTH_BRAND = r"""
    <section class="auth-brand">
      <a class="brand" href="/login"><span class="brand-mark" aria-hidden="true">J</span><span>Job Hunting Agent</span></a>
      <div>
        <h1>__HEADLINE__</h1>
        <p>__LEDE__</p>
      </div>
      <ul class="auth-points">
        <li><span class="mark" aria-hidden="true">A</span><span><b>ATS score you can act on</b>See exactly which fixes raise it, then download a validated ATS-ready resume.</span></li>
        <li><span class="mark" aria-hidden="true">J</span><span><b>Fresh, matched job leads</b>LinkedIn, Naukri and partner job boards, ranked against your skills and experience.</span></li>
        <li><span class="mark" aria-hidden="true">P</span><span><b>Practice for the real job</b>Job-specific mock tests, coding questions and interviews with daily and weekly reports.</span></li>
      </ul>
    </section>
"""

_EMAIL_CHECK_JS = r"""
    function validEmail(value) {
      const email = value.trim().toLowerCase();
      const basicEmail = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
      return email.length <= 254
        && basicEmail.test(email)
        && !email.includes('..')
        && !email.split('@')[0].startsWith('.')
        && !email.split('@')[0].endsWith('.');
    }
    function validateEmailField(input) {
      const email = input.value.trim().toLowerCase();
      input.value = email;
      input.setCustomValidity(validEmail(email) ? '' : 'Enter a valid email address like name@example.com.');
      return input.reportValidity();
    }
    function setStatus(text, kind) {
      status.textContent = text;
      status.className = `auth-status ${kind || ''}`;
    }
"""


def _auth_page(title: str, headline: str, lede: str, card: str, script: str) -> str:
    from .pages import ASSET_VERSION, head

    brand = _AUTH_BRAND.replace("__HEADLINE__", headline).replace("__LEDE__", lede)
    from .pages import language_picker

    return (
        head(title) + "</head><body class=\"ux\">"
        f'<main class="auth">{brand}<section class="auth-side"><div class="auth-lang">{language_picker()}</div><div class="auth-card">{card}</div></section></main>'
        f'<script src="/static/ui/shell.js?v={ASSET_VERSION}"></script><script>{script}</script></body></html>'
    )


def _login_page() -> str:
    card = r"""
        <div class="btn-row" style="gap:18px"><span class="step on" id="step-1"><b>1</b>Email</span><span class="step" id="step-2"><b>2</b>Code</span></div>
        <h2>Email OTP Sign In</h2>
        <p class="muted">Enter your email and we will send a one-time sign-in code. No password needed.</p>
        <form id="request-form" novalidate>
          <label class="field" for="email">Email <span class="req" aria-hidden="true">*</span><input id="email" name="email" type="email" autocomplete="email" maxlength="254" placeholder="name@example.com" pattern="^[^\s@]+@[^\s@]+\.[^\s@]{2,}$" required autofocus></label>
          <button class="btn btn-primary" id="send-otp" type="submit">Send OTP</button>
        </form>
        <form id="verify-form" class="hidden" method="post" action="/api/auth/verify">
          <input id="verify-email" name="email" type="hidden">
          <label class="field" for="otp">6-digit code<input id="otp" class="otp-input" name="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••" required></label>
          <button class="btn btn-primary" type="submit">Verify and Continue</button>
          <button class="btn btn-quiet" id="change-email" type="button">Use a different email</button>
        </form>
        <p id="status" class="auth-status" role="status" aria-live="polite"></p>
        <hr class="divider" style="margin:4px 0">
        <a href="/register">New user? Verify your email first</a>
        <a class="faint" href="/privacy">Privacy notice</a>
"""
    script = r"""
    const requestForm = document.getElementById('request-form');
    const verifyForm = document.getElementById('verify-form');
    const emailInput = document.getElementById('email');
    const verifyEmail = document.getElementById('verify-email');
    const status = document.getElementById('status');
    const sendButton = document.getElementById('send-otp');
""" + _EMAIL_CHECK_JS + r"""
    function showStep(two) {
      verifyForm.classList.toggle('hidden', !two);
      document.getElementById('step-1').classList.toggle('on', !two);
      document.getElementById('step-2').classList.toggle('on', two);
      sendButton.textContent = two ? 'Send a new code' : 'Send OTP';
      sendButton.className = two ? 'btn' : 'btn btn-primary';
      if (two) document.getElementById('otp').focus();
    }
    emailInput.addEventListener('input', () => emailInput.setCustomValidity(''));
    document.getElementById('change-email').addEventListener('click', () => { showStep(false); setStatus(''); emailInput.focus(); });
    requestForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!validateEmailField(emailInput)) {
        setStatus('Enter a valid email address like name@example.com.', 'bad');
        return;
      }
      sendButton.disabled = true;
      setStatus('Sending your code…');
      try {
        const response = await fetch('/api/auth/request-otp', { method: 'POST', body: new FormData(requestForm) });
        const payload = await UI.payloadOf(response);
        if (!response.ok) { setStatus(payload.detail || 'Unable to send OTP.', 'bad'); return; }
        verifyEmail.value = payload.email;
        showStep(true);
        setStatus(payload.dev_otp ? `OTP generated for local testing: ${payload.dev_otp}` : `OTP sent to ${payload.email}. It expires in a few minutes.`, 'good');
      } catch (_) {
        setStatus('Unable to reach the server. Check your connection and try again.', 'bad');
      } finally {
        sendButton.disabled = false;
      }
    });
"""
    return _auth_page(
        "Sign in", "Your job search, run like a pipeline.",
        "Sign in with an email OTP to access resume scoring, job discovery, recruiter draft templates, practice and daily run history.",
        card, script,
    )


def _register_page() -> str:
    card = r"""
        <h2>New User Registration</h2>
        <p class="muted">Enter your email address. AWS will send a verification email with a link that approves this address for sign-in codes.</p>
        <form id="register-form" novalidate>
          <label class="field" for="email">Email <span class="req" aria-hidden="true">*</span><input id="email" name="email" type="email" autocomplete="email" maxlength="254" placeholder="name@example.com" pattern="^[^\s@]+@[^\s@]+\.[^\s@]{2,}$" required autofocus></label>
          <button class="btn btn-primary" id="register-submit" type="submit">Send Verification Link</button>
        </form>
        <p id="status" class="auth-status" role="status" aria-live="polite"></p>
        <div class="notice"><span>After clicking the AWS verification link, come back to the login page and click Send OTP.</span></div>
        <a class="btn" href="/login">Back to Login</a>
"""
    script = r"""
    const form = document.getElementById('register-form');
    const emailInput = document.getElementById('email');
    const status = document.getElementById('status');
""" + _EMAIL_CHECK_JS + r"""
    emailInput.addEventListener('input', () => emailInput.setCustomValidity(''));
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!validateEmailField(emailInput)) {
        setStatus('Enter a valid email address like name@example.com.', 'bad');
        return;
      }
      const button = document.getElementById('register-submit');
      button.disabled = true;
      setStatus('Requesting the AWS verification email…');
      try {
        const response = await fetch('/api/auth/register-email', { method: 'POST', body: new FormData(form) });
        const payload = await UI.payloadOf(response);
        if (!response.ok) { setStatus(payload.detail || 'Unable to request verification right now.', 'bad'); return; }
        setStatus(payload.message || 'Verification email requested. Check your inbox.', 'good');
      } catch (_) {
        setStatus('Unable to reach the server. Please try again.', 'bad');
      } finally {
        button.disabled = false;
      }
    });
"""
    return _auth_page(
        "Verify your email", "Verify once, sign in with a code after.",
        "New users verify their email once through AWS SES. After verification, return to login and request your OTP normally.",
        card, script,
    )


def _mock_interview_page(user_email: str) -> str:
    from .pages import practice_nav

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Virtual Mock Interview - Job Hunting Agent</title>
  <style>
    :root {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; --ink:#142033; --muted:#8ca0bd; --blue:#2563eb; --line:#29405f; --green:#22c55e; --gold:#f59e0b; --panel:rgba(13, 25, 43, .92); --panel2:rgba(17, 31, 52, .96); }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; color:#eef6ff; background: radial-gradient(circle at 50% 20%, rgba(37,99,235,.35), transparent 34%), linear-gradient(120deg, rgba(5, 14, 29, .95), rgba(9, 22, 41, .88)), url('/static/job-search-hero.png'); background-size: cover; background-attachment: fixed; }}
    .topbar {{ width:min(1360px, calc(100% - 36px)); margin:0 auto; padding:14px 0; display:flex; justify-content:space-between; gap:12px; align-items:center; color:#fff; }}
    .topbar a, .topbar button {{ min-height:36px; border:0; border-radius:7px; padding:8px 13px; font-weight:850; text-decoration:none; cursor:pointer; }}
    .topbar a {{ background:rgba(255,255,255,.94); color:#152238; }}
    .topbar form {{ margin:0; }}
    .topbar button {{ background:#175cd3; color:#fff; }}
    .user-chip {{ padding:8px 12px; border:1px solid rgba(255,255,255,.28); border-radius:999px; background:rgba(255,255,255,.11); font-size:13px; font-weight:800; }}
    main {{ width:min(1360px, calc(100% - 36px)); margin:6px auto 36px; }}
    .studio-shell {{ border:1px solid rgba(148,163,184,.35); border-radius:10px; background:rgba(6,16,31,.82); box-shadow:0 30px 90px rgba(0,0,0,.45); overflow:hidden; }}
    .studio-top {{ display:flex; justify-content:space-between; gap:12px; align-items:center; min-height:48px; padding:10px 14px; background:#0b1424; border-bottom:1px solid rgba(148,163,184,.26); }}
    .brand {{ display:flex; align-items:center; gap:10px; font-weight:950; }}
    .brand-mark {{ width:30px; height:30px; border-radius:50%; display:grid; place-items:center; background:#1d4ed8; color:#fff; }}
    .session-stats {{ display:flex; flex-wrap:wrap; gap:14px; color:#cbd5e1; font-size:13px; font-weight:800; }}
    .session-stats strong {{ color:#fff; }}
    .interview-grid {{ display:grid; grid-template-columns:300px minmax(380px,1fr) 330px; gap:12px; min-height:650px; padding:12px; }}
    .room-panel {{ border:1px solid rgba(148,163,184,.32); border-radius:8px; background:var(--panel); box-shadow:inset 0 1px 0 rgba(255,255,255,.05); overflow:hidden; }}
    .panel-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; padding:12px 14px; border-bottom:1px solid rgba(148,163,184,.22); background:rgba(15, 29, 49, .9); }}
    .panel-title {{ margin:0; font-size:15px; color:#dbeafe; }}
    .pill {{ display:inline-flex; min-height:24px; align-items:center; padding:4px 8px; border-radius:999px; background:rgba(37,99,235,.18); color:#bfdbfe; border:1px solid rgba(96,165,250,.35); font-size:12px; font-weight:900; }}
    .question-body {{ padding:14px; }}
    .question-text {{ margin:10px 0 0; color:#fff; font-size:17px; line-height:1.45; font-weight:800; }}
    .code-box {{ margin-top:14px; min-height:180px; padding:12px; border-radius:7px; background:#050b16; color:#9ee7ff; border:1px solid rgba(148,163,184,.26); font:12px/1.55 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space:pre-wrap; }}
    .stage {{ position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:650px; background:linear-gradient(180deg,#1264d8,#0d8ce3 48%,#0c4a6e); }}
    .stage::before {{ content:""; position:absolute; inset:0; background-image:linear-gradient(rgba(255,255,255,.16) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.12) 1px, transparent 1px); background-size:70px 70px; opacity:.22; }}
    .stage-logo {{ position:absolute; inset:22px; display:grid; grid-template-columns:repeat(3,1fr); gap:28px; opacity:.18; color:#fff; font-weight:950; font-size:20px; pointer-events:none; }}
    .agent-avatar {{ position:relative; width:min(380px, 76%); aspect-ratio:1; border-radius:50%; background:linear-gradient(135deg,#334155,#0f172a); background-image:url('/static/ai-interviewer-sarah.png'); background-size:cover; background-position:center; box-shadow:0 30px 70px rgba(0,0,0,.42), 0 0 0 14px rgba(15,23,42,.45); border:8px solid rgba(255,255,255,.22); overflow:hidden; }}
    .agent-avatar::after {{ content:""; position:absolute; inset:0; border-radius:inherit; box-shadow:inset 0 -42px 70px rgba(15,23,42,.28), inset 0 0 0 1px rgba(255,255,255,.18); pointer-events:none; }}
    .agent-badge {{ position:relative; margin-top:-26px; padding:9px 16px; border-radius:999px; background:rgba(2,6,23,.82); border:1px solid rgba(255,255,255,.22); color:#fff; font-weight:900; text-align:center; }}
    .agent-badge small {{ display:block; margin-top:2px; color:#bfdbfe; font-size:11px; }}
    .stage-controls {{ position:absolute; left:50%; bottom:18px; transform:translateX(-50%); display:flex; gap:10px; align-items:center; padding:8px; border-radius:999px; background:rgba(2,6,23,.6); border:1px solid rgba(255,255,255,.2); }}
    button, .button {{ border:0; border-radius:7px; min-height:40px; padding:10px 13px; font-weight:900; cursor:pointer; text-decoration:none; display:inline-flex; align-items:center; justify-content:center; }}
    .primary {{ background:var(--blue); color:#fff; }}
    .dark {{ background:#1f2937; color:#fff; }}
    .ghost {{ background:#eaf2ff; color:#175cd3; }}
    .danger {{ background:#dc2626; color:#fff; }}
    .warn {{ background:#f59e0b; color:#111827; }}
    button:disabled {{ opacity:.55; cursor:not-allowed; }}
    .right-stack {{ display:grid; grid-template-rows:185px minmax(330px,1fr); gap:12px; }}
    .camera-card {{ position:relative; background:#020617; }}
    video {{ width:100%; height:100%; object-fit:cover; display:block; background:#111827; }}
    .camera-placeholder {{ position:absolute; inset:0; display:grid; place-items:center; padding:16px; color:#cbd5e1; text-align:center; background:linear-gradient(135deg,#0f172a,#1e293b); }}
    .camera-label {{ position:absolute; left:10px; bottom:10px; padding:5px 8px; border-radius:999px; background:rgba(2,6,23,.78); color:#fff; font-size:12px; font-weight:900; }}
    .answer-area {{ display:flex; flex-direction:column; min-height:0; }}
    .mic-orb {{ width:58px; height:58px; margin:16px auto 10px; border-radius:50%; display:grid; place-items:center; color:#fff; background:radial-gradient(circle,#38bdf8,#2563eb); box-shadow:0 0 0 10px rgba(37,99,235,.14); font-weight:950; }}
    label {{ display:block; font-weight:850; color:#dbeafe; margin:10px 14px 6px; }}
    select, textarea {{ width:100%; border:1px solid rgba(148,163,184,.45); border-radius:7px; padding:10px 11px; font:inherit; color:#eef6ff; background:rgba(15,23,42,.88); }}
    textarea {{ min-height:210px; resize:vertical; line-height:1.45; }}
    .answer-pad {{ padding:0 14px 14px; }}
    .code-answer {{ padding:10px 14px 0; }}
    .editor-toolbar {{ display:grid; grid-template-columns:minmax(0,1fr) 150px; gap:10px; align-items:end; margin-bottom:8px; }}
    .editor-toolbar label {{ margin:0 0 6px; }}
    .editor-note {{ margin:0; color:#cbd5e1; font-size:12px; line-height:1.4; }}
    .code-editor {{ min-height:280px; resize:vertical; tab-size:2; white-space:pre; overflow:auto; color:#dbeafe; background:#050b16; font:13px/1.55 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
    .transcript-code {{ margin:8px 0 0; max-height:260px; overflow:auto; padding:10px; border:1px solid rgba(148,163,184,.25); border-radius:6px; color:#dbeafe; background:#050b16; font:12px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space:pre; }}
    .language-chip {{ display:inline-flex; margin-top:5px; color:#93c5fd; font-size:11px; font-weight:850; }}
    .button-row {{ display:flex; flex-wrap:wrap; gap:9px; margin-top:12px; }}
    .setup-panel {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:12px; padding:14px; border:1px solid rgba(148,163,184,.3); border-radius:8px; background:rgba(15,23,42,.72); }}
    .setup-panel h2 {{ margin:0; font-size:18px; }}
    .setup-panel p {{ margin:6px 0 0; color:#cbd5e1; line-height:1.45; }}
    .setup-actions {{ display:flex; align-items:end; gap:10px; flex-wrap:wrap; }}
    .progress {{ height:9px; border-radius:999px; background:#1e293b; overflow:hidden; }}
    .progress > span {{ display:block; height:100%; width:0%; background:#38bdf8; transition:width .2s ease; }}
    .stat-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:12px; }}
    .stat {{ border:1px solid rgba(148,163,184,.3); border-radius:8px; padding:10px; background:rgba(15,23,42,.75); }}
    .stat strong {{ display:block; font-size:24px; color:#fff; }}
    .stat span, .muted {{ color:#cbd5e1; }}
    .transcript {{ display:grid; gap:10px; max-height:270px; overflow:auto; padding:12px; }}
    .turn {{ border:1px solid rgba(148,163,184,.28); border-radius:8px; padding:11px; background:rgba(15,23,42,.72); color:#e5edf8; }}
    .turn strong {{ display:block; margin-bottom:6px; color:#fff; }}
    .score {{ display:grid; grid-template-columns:140px minmax(0,1fr); gap:16px; align-items:center; }}
    .score-circle {{ width:118px; height:118px; border-radius:50%; display:grid; place-items:center; background:conic-gradient(#38bdf8 calc(var(--score,0) * 1%), #1e293b 0); }}
    .score-circle span {{ width:88px; height:88px; border-radius:50%; display:grid; place-items:center; background:#0f172a; color:#fff; font-size:30px; font-weight:950; }}
    .report-meta {{ margin-top:5px; color:#93c5fd; font-size:12px; font-weight:850; }}
    .feedback-columns {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; margin-top:20px; }}
    .feedback-list {{ margin:10px 0 0; padding-left:22px; }}
    .feedback-list li {{ margin:7px 0; line-height:1.4; }}
    .report-section {{ margin-top:22px; padding-top:18px; border-top:1px solid rgba(148,163,184,.25); }}
    .rubric-list {{ display:grid; gap:10px; margin-top:12px; }}
    .rubric-row {{ display:grid; grid-template-columns:150px minmax(0,1fr) 45px; gap:10px; align-items:center; }}
    .rubric-track {{ height:9px; border-radius:999px; background:#1e293b; overflow:hidden; }}
    .rubric-track span {{ display:block; height:100%; background:#38bdf8; }}
    .rubric-value {{ color:#fff; font-weight:900; text-align:right; }}
    .plan-list {{ display:grid; gap:0; margin-top:12px; }}
    .plan-step {{ display:grid; grid-template-columns:34px minmax(0,1fr); gap:12px; padding:14px 0; border-bottom:1px solid rgba(148,163,184,.2); }}
    .plan-step:last-child {{ border-bottom:0; }}
    .plan-number {{ width:30px; height:30px; border-radius:50%; display:grid; place-items:center; background:#2563eb; color:#fff; font-weight:900; }}
    .plan-step h4 {{ margin:0 0 5px; color:#fff; }}
    .plan-step p {{ margin:4px 0; line-height:1.45; }}
    .answer-review {{ padding:11px 0; border-bottom:1px solid rgba(148,163,184,.2); }}
    .answer-review summary {{ cursor:pointer; color:#fff; font-weight:850; }}
    .answer-review p {{ line-height:1.45; }}
    .hidden {{ display:none !important; }}
    .notice {{ margin-top:12px; padding:10px; border:1px solid rgba(245,158,11,.5); border-radius:8px; color:#fde68a; background:rgba(120,53,15,.28); }}
    @media (max-width: 1100px) {{ .interview-grid, .setup-panel, .feedback-columns {{ grid-template-columns:1fr; }} .right-stack {{ grid-template-rows:auto; }} .stage {{ min-height:480px; }} .topbar {{ width:min(100% - 28px, 760px); flex-wrap:wrap; }} main {{ width:min(100% - 28px, 760px); }} .stat-grid {{ grid-template-columns:1fr; }} }}
    @media (max-width: 620px) {{ .score {{ grid-template-columns:1fr; }} .rubric-row {{ grid-template-columns:115px minmax(0,1fr) 38px; }} }}
  </style>
</head>
<body>
  {practice_nav("mock-interview", user_email)}
  <main>
    <section class="studio-shell">
      <header class="studio-top">
        <div class="brand"><span class="brand-mark">JH</span><span>Mock Interview Agent · Virtual Interview Studio</span></div>
        <div class="session-stats"><span>Elapsed <strong id="timer">00:00</strong></span><span>Progress <strong id="progress-label">0/0</strong></span><span>Voice <strong id="accent-label">Indian English</strong></span></div>
      </header>
      <section class="setup-panel">
        <div>
          <h2>Interview Setup</h2>
          <p>Pick a job lead to practise for that exact role, then choose accent, length, and camera.</p>
          <label for="job-select">Job lead</label>
          <select id="job-select"><option value="">General practice (profile roles)</option></select>
        </div>
        <div>
          <label for="region">Interviewer accent</label>
          <select id="region">
            <option value="India">Indian English</option>
            <option value="United States">American English</option>
            <option value="United Kingdom">British English</option>
            <option value="Australia">Australian English</option>
            <option value="Canada">Canadian English</option>
            <option value="Singapore">Singapore English</option>
          </select>
          <button id="preview-accent" class="ghost" type="button" disabled>Preview voice</button>
          <p id="voice-availability" role="status" aria-live="polite">Checking regional voices...</p>
        </div>
        <div>
          <label for="question-limit">Interview length</label>
          <select id="question-limit">
            <option value="standard">Standard - 8 balanced questions</option>
            <option value="quick">Quick confidence round - 5 foundation questions</option>
            <option value="deep">Deep practice - 10 advanced questions</option>
          </select>
        </div>
        <div class="setup-actions">
          <button id="camera-btn" class="ghost" type="button">Enable Camera</button>
          <button id="start-btn" class="primary" type="button">Start Interview</button>
          <button id="stop-btn" class="danger hidden" type="button">End</button>
        </div>
      </section>
      <div class="progress"><span id="progress-bar"></span></div>
      <section class="interview-grid">
        <aside class="room-panel">
          <div class="panel-head"><h2 class="panel-title">Current Question</h2><span id="question-count-pill" class="pill">Ready</span></div>
          <div class="question-body">
            <span id="category" class="pill">Interview</span>
            <p id="question-text" class="question-text">Start the interview to receive the first role-specific question.</p>
            <div id="code-box" class="code-box">Interview context will adapt to your target roles and skills.\n\nDetected focus areas:\n- Loading profile signals...</div>
            <div class="notice">Tip: answer with situation, technical action, tradeoff, and measurable result.</div>
          </div>
        </aside>
        <section class="room-panel stage">
          <div class="stage-logo"><span>Job Hunt</span><span>ATS</span><span>Mock</span><span>Data</span><span>Career</span><span>Agent</span></div>
          <div class="agent-avatar" aria-label="AI interviewer avatar"></div>
          <div class="agent-badge">AI Interviewer - Sarah<small id="agent-status">Ready to begin a professional mock interview.</small></div>
          <div class="stage-controls">
            <button id="speak-btn" class="ghost" type="button" disabled>Replay</button>
            <button id="record-btn" class="primary" type="button" disabled>Record</button>
          </div>
        </section>
        <aside class="right-stack">
          <section class="room-panel camera-card">
            <video id="camera-preview" autoplay muted playsinline></video>
            <div id="camera-placeholder" class="camera-placeholder">Camera preview appears here after permission is granted.</div>
            <span class="camera-label">Your video</span>
          </section>
          <section class="room-panel answer-area">
            <div class="panel-head"><h2 id="answer-panel-title" class="panel-title">Your Answer</h2><span id="recording-state" class="pill">Idle</span></div>
            <div id="spoken-answer">
              <div class="mic-orb">MIC</div>
              <label for="answer">Response transcript</label>
              <div class="answer-pad">
              <textarea id="answer" placeholder="Speak after clicking Record, or type your answer here. Use examples, technical depth, and measurable impact."></textarea>
              </div>
            </div>
            <div id="code-answer" class="code-answer hidden">
              <div class="editor-toolbar">
                <div>
                  <label for="code-editor">Code response</label>
                  <p class="editor-note">Coding problems: press Run sample tests to check your code. It runs only in your browser, never on our server.</p>
                </div>
                <div>
                  <label for="code-language">Language</label>
                  <select id="code-language">
                    <option value="sql">SQL</option><option value="python">Python</option><option value="cpp">C++</option><option value="c">C</option>
                    <option value="java">Java</option><option value="javascript">JavaScript</option><option value="typescript">TypeScript</option>
                    <option value="csharp">C#</option><option value="go">Go</option><option value="rust">Rust</option>
                    <option value="php">PHP</option><option value="ruby">Ruby</option><option value="kotlin">Kotlin</option>
                    <option value="swift">Swift</option><option value="scala">Scala</option><option value="r">R</option>
                    <option value="shell">Shell</option><option value="html">HTML/CSS</option><option value="dart">Dart</option>
                    <option value="matlab">MATLAB</option><option value="perl">Perl</option><option value="lua">Lua</option>
                    <option value="graphql">GraphQL</option><option value="mongodb">MongoDB Query</option><option value="plaintext">Other / Plain text</option>
                  </select>
                </div>
              </div>
              <textarea id="code-editor" class="code-editor" aria-label="Code response editor" autocomplete="off" autocapitalize="off" spellcheck="false" wrap="off" placeholder="Write your solution here..."></textarea>
            </div>
            <div class="answer-pad">
              <div class="button-row">
                <button id="save-btn" class="primary" type="button" disabled>Submit & Next</button>
                <button id="clear-btn" class="dark" type="button">Clear</button>
              </div>
            </div>
          </section>
        </aside>
      </section>
      <section id="scorecard" class="room-panel hidden" style="margin:12px;padding:16px"></section>
      <section class="room-panel" style="margin:12px">
        <div class="panel-head"><h2 class="panel-title">Interview Transcript</h2><span class="pill">User specific</span></div>
        <div id="transcript" class="transcript"></div>
      </section>
      <section id="history" class="room-panel" style="margin:12px;padding:14px"></section>
    </section>
  </main>
  <script src="/static/code_runner.js"></script>
  <script src="/static/interview_coding.js"></script>
  <script>
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const speakBtn = document.getElementById('speak-btn');
    const recordBtn = document.getElementById('record-btn');
    const saveBtn = document.getElementById('save-btn');
    const clearBtn = document.getElementById('clear-btn');
    const cameraBtn = document.getElementById('camera-btn');
    const region = document.getElementById('region');
    const previewAccent = document.getElementById('preview-accent');
    const voiceAvailability = document.getElementById('voice-availability');
    let accentCatalog = null;
    let previewGeneration = 0;
    let previewAudio = null;
    let previewUrl = null;
    const questionLimit = document.getElementById('question-limit');
    const answer = document.getElementById('answer');
    const spokenAnswer = document.getElementById('spoken-answer');
    const codeAnswer = document.getElementById('code-answer');
    const codeEditor = document.getElementById('code-editor');
    const codeLanguage = document.getElementById('code-language');
    const answerPanelTitle = document.getElementById('answer-panel-title');
    const questionText = document.getElementById('question-text');
    const category = document.getElementById('category');
    const codeBox = document.getElementById('code-box');
    const statusText = document.getElementById('agent-status');
    const timer = document.getElementById('timer');
    const progressLabel = document.getElementById('progress-label');
    const progressBar = document.getElementById('progress-bar');
    const accentLabel = document.getElementById('accent-label');
    const transcript = document.getElementById('transcript');
    const scorecard = document.getElementById('scorecard');
    const historyPanel = document.getElementById('history');
    const jobSelect = document.getElementById('job-select');
    const questionCountPill = document.getElementById('question-count-pill');
    const recordingState = document.getElementById('recording-state');
    const cameraPreview = document.getElementById('camera-preview');
    const cameraPlaceholder = document.getElementById('camera-placeholder');
    let session = null;
    let activeIndex = 0;
    let answers = [];
    let startedAt = null;
    let timerId = null;
    let recognition = null;
    let recognitionActive = false;
    let recognitionBase = '';
    let recognitionRestartTimer = null;
    let mediaStream = null;
    let interviewerAudio = null;
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, (char) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[char]));
    }}
    function formatTime(seconds) {{
      const mins = String(Math.floor(seconds / 60)).padStart(2, '0');
      const secs = String(seconds % 60).padStart(2, '0');
      return `${{mins}}:${{secs}}`;
    }}
    function tickTimer() {{
      if (!startedAt) return;
      timer.textContent = formatTime(Math.floor((Date.now() - startedAt) / 1000));
    }}
    function stopCamera() {{
      if (mediaStream) {{
        mediaStream.getTracks().forEach((track) => track.stop());
      }}
      mediaStream = null;
      cameraPreview.srcObject = null;
      cameraPlaceholder.textContent = 'Camera preview appears here after permission is granted.';
      cameraPlaceholder.classList.remove('hidden');
      cameraBtn.textContent = 'Enable Camera';
    }}
    async function enableCamera() {{
      if (mediaStream) {{
        stopCamera();
        return;
      }}
      try {{
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
          cameraPlaceholder.textContent = 'Camera preview is not available in this browser. Interview can continue without video.';
          return;
        }}
        mediaStream = await navigator.mediaDevices.getUserMedia({{ video: true, audio: false }});
        cameraPreview.srcObject = mediaStream;
        cameraPlaceholder.classList.add('hidden');
        cameraBtn.textContent = 'Turn Camera Off';
      }} catch (error) {{
        cameraPlaceholder.textContent = 'Camera permission was not granted. Interview can continue without video.';
      }}
    }}
    function preferredVoice(voiceProfile) {{
      const voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
      const targetLanguage = String(voiceProfile?.lang || '').toLowerCase().replace('_', '-');
      const hints = (voiceProfile?.female_voice_hints || []).map((hint) => hint.toLowerCase());
      const maleHints = (voiceProfile?.male_voice_hints || []).map((hint) => hint.toLowerCase());
      const exactVoices = voices.filter((voice) => String(voice.lang || '').toLowerCase().replace('_', '-') === targetLanguage);
      const knownFemaleExact = exactVoices.find((voice) => {{
        const name = String(voice.name || '').toLowerCase();
        return hints.some((hint) => name.includes(hint)) && !maleHints.some((hint) => name.includes(hint));
      }});
      if (knownFemaleExact) return knownFemaleExact;
      return null;
    }}
    async function waitForVoices() {{
      if (!window.speechSynthesis || window.speechSynthesis.getVoices().length) return;
      await new Promise((resolve) => {{
        const timeout = setTimeout(resolve, 1200);
        window.speechSynthesis.addEventListener('voiceschanged', () => {{ clearTimeout(timeout); resolve(); }}, {{ once: true }});
      }});
    }}
    async function speak(text, questionId) {{
      if (session?.tts_provider === 'azure') {{
        try {{
          if (interviewerAudio) interviewerAudio.pause();
          const response = await fetch('/api/mock-interview/speech', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{session_id: session.session_id, question_id: questionId}})
          }});
          if (response.ok) {{
            const audioUrl = URL.createObjectURL(await response.blob());
            interviewerAudio = new Audio(audioUrl);
            interviewerAudio.addEventListener('ended', () => URL.revokeObjectURL(audioUrl), {{once:true}});
            accentLabel.textContent = `${{session.accent}} · Sarah neural`;
            await interviewerAudio.play();
            return;
          }}
        }} catch (error) {{
          statusText.textContent = 'Neural speech was unavailable; trying an installed browser voice.';
        }}
      }}
      if (!window.speechSynthesis || !session) return;
      window.speechSynthesis.cancel();
      const voice = preferredVoice(session.voice);
      if (!voice) {{
        speakBtn.disabled = true;
        accentLabel.textContent = `${{session.accent}} · compatible voice unavailable`;
        statusText.textContent = `The selected ${{session.accent}} female voice is unavailable. Configure Azure Speech or install a matching regional female voice. Text questions remain available.`;
        return;
      }}
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = session.voice.lang;
      utterance.voice = voice;
      utterance.rate = 0.92;
      utterance.pitch = 1;
      accentLabel.textContent = `${{session.accent}} · ${{voice.name}}`;
      window.speechSynthesis.speak(utterance);
    }}
    function renderQuestion() {{
      const item = session.questions[activeIndex];
      category.textContent = item.category;
      questionText.textContent = item.question;
      answer.value = '';
      codeEditor.value = '';
      recognitionBase = '';
      setAnswerMode(item);
      const total = session.questions.length;
      questionCountPill.textContent = `${{activeIndex + 1}}/${{total}}`;
      progressLabel.textContent = `${{Math.min(activeIndex + 1, total)}}/${{total}}`;
      progressBar.style.width = `${{Math.round((activeIndex / total) * 100)}}%`;
      codeBox.textContent = `Focus: ${{item.tag || item.category}}\n\nPrompt type: ${{item.category}}\n\nListen fully, pause, then answer with a real project example.`;
      window.InterviewCoding?.render(item);
      statusText.textContent = `Question ${{activeIndex + 1}} of ${{total}} · Listening...`;
      speak(item.question, item.id);
    }}
    function renderTranscript() {{
      transcript.innerHTML = answers.map((item, index) => `
        <article class="turn">
          <strong>Q${{index + 1}}. ${{escapeHtml(item.question)}}</strong>
          ${{item.answer_type === 'code'
            ? `<span class="language-chip">${{escapeHtml(languageLabel(item.code_language))}}</span><pre class="transcript-code"><code>${{escapeHtml(item.answer || 'No code submitted.')}}</code></pre>`
            : `<div>${{escapeHtml(item.answer || 'No answer captured.')}}</div>`}}
        </article>
      `).join('') || '<div class="turn">No answers captured yet.</div>';
    }}
    function languageLabel(value) {{
      const option = [...codeLanguage.options].find((item) => item.value === value);
      return option ? option.textContent : 'Code';
    }}
    function setAnswerMode(item) {{
      const codeMode = item?.answer_mode === 'code';
      spokenAnswer.classList.toggle('hidden', codeMode);
      codeAnswer.classList.toggle('hidden', !codeMode);
      answerPanelTitle.textContent = codeMode ? 'Code Answer' : 'Your Answer';
      recordingState.textContent = codeMode ? 'Editor' : 'Idle';
      recordBtn.disabled = codeMode || !session;
      if (codeMode) {{
        const supported = [...codeLanguage.options].some((option) => option.value === item.editor_language);
        codeLanguage.value = supported ? item.editor_language : 'plaintext';
        codeEditor.focus();
      }}
    }}
    function setInterviewActive(active) {{
      startBtn.disabled = active;
      region.disabled = active;
      jobSelect.disabled = active;
      previewAccent.disabled = active || !accentCatalog;
      stopBtn.classList.toggle('hidden', !active);
      speakBtn.disabled = !active || (session?.tts_provider !== 'azure' && !preferredVoice(session?.voice || {{}}));
      recordBtn.disabled = !active || session?.questions?.[activeIndex]?.answer_mode === 'code';
      saveBtn.disabled = !active;
      if (!active) updateAccentAvailability();
    }}
    let interviewJobs = [];
    let jobsLoaded = false;
    function selectedInterviewJob() {{
      return jobSelect.value === '' ? null : interviewJobs[Number(jobSelect.value)];
    }}
    async function loadQuestions() {{
      const job = selectedInterviewJob();
      const query = job ? `?job_id=${{encodeURIComponent(job.job_id)}}&run_id=${{encodeURIComponent(job.run_id || 0)}}` : '';
      const response = await fetch('/api/mock-interview/questions' + query);
      const payload = await response.json();
      if (!response.ok) {{
        statusText.textContent = payload.detail || 'Unable to load interview context.';
        return;
      }}
      if (!jobsLoaded) {{
        jobsLoaded = true;
        interviewJobs = payload.jobs || [];
        jobSelect.innerHTML = '<option value="">General practice (profile roles)</option>' + interviewJobs.map((item, index) =>
          `<option value="${{index}}">${{escapeHtml(item.title)}}${{item.company ? ' · ' + escapeHtml(item.company) : ''}}${{item.match_score ? ' · ' + item.match_score + '% match' : ''}}</option>`).join('');
        const wanted = new URLSearchParams(window.location.search).get('job');
        const index = wanted ? interviewJobs.findIndex((item) => item.job_id === wanted) : -1;
        if (index >= 0) {{
          jobSelect.value = String(index);
          return loadQuestions();
        }}
      }}
      const nl = String.fromCharCode(10);
      const levelNames = {{ entry: 'Entry level (0-2 years)', mid: 'Mid level (2-5 years)', senior: 'Senior (5+ years)' }};
      const coding = payload.coding_slots || {{}};
      const levelLine = `Level: ${{levelNames[payload.level] || 'Mid level'}}${{coding.standard ? ` · coding problems: ${{coding.quick}} quick / ${{coding.standard}} standard / ${{coding.deep}} deep` : ''}}`;
      if (payload.job) {{
        const lines = [`Job-specific interview: ${{payload.job.title}}${{payload.job.company ? ' at ' + payload.job.company : ''}}`, levelLine];
        if (payload.job.skills.length) lines.push('', 'Skills the role needs that you can show:', ...payload.job.skills.slice(0, 8).map((item) => `- ${{item}}`));
        if (payload.job.gaps.length) lines.push('', 'Gaps to prepare for:', ...payload.job.gaps.map((item) => `- ${{item}}`));
        if (payload.job.responsibilities.length) lines.push('', 'From the posting:', ...payload.job.responsibilities.map((item) => `- ${{item}}`));
        if (!payload.job.has_description) lines.push('', 'The portal did not share a full description, so questions use the job title and skills.');
        codeBox.textContent = lines.join(nl);
        return;
      }}
      const focusAreas = [...(payload.roles || []), ...(payload.skills || []).slice(0, 7)];
      const focusLines = focusAreas.length
        ? focusAreas.map((item) => `- ${{item}}`)
        : ['- Add target roles and skills on the dashboard.'];
      codeBox.textContent = [levelLine, '', 'Detected focus areas:', ...focusLines].join(nl);
    }}
    jobSelect.addEventListener('change', loadQuestions);
    async function loadHistory() {{
      const response = await fetch('/api/mock-interview/history');
      if (!response.ok) return;
      const payload = await response.json();
      const sessions = payload.sessions || [];
      historyPanel.innerHTML = `<h3>Recent Interviews</h3>` + (sessions.length ? sessions.map((item) => `
        <div class="turn" style="margin-top:10px">
          <strong>${{escapeHtml(item.job_title || 'General practice')}} · ${{item.score || 0}}/100</strong>
          <span class="muted">${{escapeHtml(item.company ? item.company + ' · ' : '')}}${{escapeHtml(item.accent)}}</span>
          <span class="muted">${{escapeHtml(item.completed_at || item.started_at || '')}}</span>
        </div>
      `).join('') : '<p class="muted">No completed interviews yet.</p>');
    }}
    async function startInterview() {{
      stopAccentPreview();
      region.disabled = true;
      jobSelect.disabled = true;
      previewAccent.disabled = true;
      startBtn.disabled = true;
      try {{
      const response = await fetch('/api/mock-interview/start', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{region: region.value, interview_mode: questionLimit.value, job_id: selectedInterviewJob()?.job_id || '', run_id: selectedInterviewJob()?.run_id || 0}})
      }});
      const payload = await response.json();
      if (!response.ok) {{
        statusText.textContent = payload.detail || 'Unable to start interview.';
        setInterviewActive(false);
        return;
      }}
      await waitForVoices();
      session = payload;
      activeIndex = 0;
      answers = [];
      startedAt = Date.now();
      clearInterval(timerId);
      timerId = setInterval(tickTimer, 1000);
      tickTimer();
      accentLabel.textContent = session.accent;
      setInterviewActive(true);
      scorecard.classList.add('hidden');
      renderTranscript();
      renderQuestion();
      }} catch (error) {{
        statusText.textContent = 'Unable to start interview. Please retry.';
        setInterviewActive(false);
      }}
    }}
    function setupRecognition() {{
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) return null;
      const rec = new Recognition();
      rec.continuous = true;
      rec.interimResults = true;
      rec.maxAlternatives = 3;
      rec.lang = session ? session.voice.lang : 'en-IN';
      rec.onresult = (event) => {{
        let finalText = '';
        let interimText = '';
        for (let i = 0; i < event.results.length; i++) {{
          const segment = event.results[i][0].transcript.trim();
          if (event.results[i].isFinal) finalText += `${{segment}} `;
          else interimText += `${{segment}} `;
        }}
        answer.value = [recognitionBase, finalText.trim(), interimText.trim()].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
      }};
      rec.onerror = (event) => {{
        if (event.error === 'no-speech') return;
        if (event.error !== 'aborted') {{
          recognitionActive = false;
          statusText.textContent = `Microphone recognition stopped (${{event.error}}). Your captured text is preserved and you can continue typing.`;
        }}
      }};
      rec.onend = () => {{
        recognitionBase = answer.value.trim();
        if (recognitionActive) {{
          recordingState.textContent = 'Listening · pause-safe';
          clearTimeout(recognitionRestartTimer);
          recognitionRestartTimer = setTimeout(() => {{
            if (!recognitionActive) return;
            recognition = setupRecognition();
            try {{ recognition.start(); }} catch (error) {{ recognitionActive = false; }}
          }}, 250);
        }} else {{
          recordBtn.textContent = 'Record';
          recordingState.textContent = 'Idle';
          recognition = null;
        }}
      }};
      return rec;
    }}
    function recordAnswer() {{
      if (recognitionActive) {{
        recognitionActive = false;
        clearTimeout(recognitionRestartTimer);
        recognition.stop();
        recordBtn.textContent = 'Record';
        recordingState.textContent = 'Idle';
        return;
      }}
      recognition = setupRecognition();
      if (!recognition) {{
        statusText.textContent = 'Speech recognition is not available in this browser. Type your answer and continue.';
        return;
      }}
      recognitionBase = answer.value.trim();
      recognitionActive = true;
      recordBtn.textContent = 'Stop';
      recordingState.textContent = 'Listening · pause-safe';
      recognition.start();
    }}
    async function saveAnswer(next = true) {{
      if (!session) return;
      if (recognition) {{
        recognitionActive = false;
        clearTimeout(recognitionRestartTimer);
        recognition.stop();
      }}
      const item = session.questions[activeIndex];
      const codeMode = item.answer_mode === 'code';
      const response = codeMode ? codeEditor.value.trim() : answer.value.trim();
      answers.push({{
        question_id: item.id,
        category: item.category,
        question: item.question,
        answer: response,
        answer_type: codeMode ? 'code' : 'text',
        code_language: codeMode ? codeLanguage.value : '',
        test_results: codeMode ? (window.InterviewCoding?.results(item.id) || null) : null,
      }});
      renderTranscript();
      if (next && activeIndex < session.questions.length - 1) {{
        activeIndex += 1;
        renderQuestion();
      }} else {{
        await finishInterview();
      }}
    }}
    async function finishInterview() {{
      if (!session) return;
      clearInterval(timerId);
      progressBar.style.width = '100%';
      setInterviewActive(false);
      statusText.textContent = 'Interview completed. Building your performance scorecard.';
      const response = await fetch('/api/mock-interview/complete', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{session_id: session.session_id, questions: session.questions, answers}})
      }});
      const payload = await response.json();
      if (!response.ok) {{
        statusText.textContent = payload.detail || 'Unable to save interview.';
        return;
      }}
      renderScorecard(payload.scorecard);
      loadHistory();
    }}
    function renderScorecard(card) {{
      scorecard.classList.remove('hidden');
      const mode = card.evaluation_mode === 'hybrid_ai' ? 'AI-assisted evaluation' : 'Evidence-based evaluation';
      const list = (items) => (items || []).map((item) => `<li>${{escapeHtml(item)}}</li>`).join('');
      const rubric = Object.entries(card.rubric || {{}}).map(([name, value]) => `
        <div class="rubric-row">
          <span>${{escapeHtml(name)}}</span>
          <div class="rubric-track" aria-hidden="true"><span style="width:${{Math.max(0, Math.min(100, Number(value) || 0))}}%"></span></div>
          <span class="rubric-value">${{escapeHtml(value)}}</span>
        </div>`).join('');
      const plan = (card.preparation_plan || []).map((step, index) => `
        <div class="plan-step">
          <span class="plan-number">${{index + 1}}</span>
          <div>
            <h4>${{escapeHtml(step.title || step.focus)}}</h4>
            <p>${{escapeHtml(step.action)}}</p>
            <p class="muted"><strong>Practice:</strong> ${{escapeHtml(step.practice)}} <strong>Target:</strong> ${{escapeHtml(step.target)}}</p>
          </div>
        </div>`).join('');
      const answerReview = (card.answers || []).map((item, index) => `
        <details class="answer-review">
          <summary>Question ${{index + 1}} · ${{escapeHtml(item.category)}} · ${{escapeHtml(item.score)}}/100</summary>
          <p><strong>${{escapeHtml(item.question)}}</strong></p>
          <p class="muted">${{escapeHtml(item.answer_type === 'code' ? 'Code response · ' + (item.code_language || 'plain text') : item.answer || 'No answer submitted.')}}</p>
          ${{(item.improvements || []).length ? `<ul class="feedback-list">${{list(item.improvements)}}</ul>` : ''}}
          ${{window.InterviewCoding ? window.InterviewCoding.reviewHtml(item, escapeHtml) : ''}}
        </details>`).join('');
      scorecard.innerHTML = `
        <div class="score">
          <div class="score-circle" style="--score:${{card.score || 0}}"><span>${{card.score || 0}}</span></div>
          <div>
            <h2>${{escapeHtml(card.confidence)}} interview readiness</h2>
            <p class="muted">${{escapeHtml(card.summary)}}</p>
            <div class="report-meta">${{escapeHtml(mode)}} · ${{escapeHtml(card.answered || 0)}} of ${{escapeHtml(card.question_count || 0)}} answered</div>
          </div>
        </div>
        <div class="feedback-columns">
          <div><h3>Strengths</h3><ul class="feedback-list">${{list(card.strengths)}}</ul></div>
          <div><h3>Weaknesses</h3><ul class="feedback-list">${{list(card.weaknesses)}}</ul></div>
          <div><h3>Improvement areas</h3><ul class="feedback-list">${{list(card.improvement_areas || card.improvements)}}</ul></div>
        </div>
        <section class="report-section"><h3>Performance dimensions</h3><div class="rubric-list">${{rubric}}</div></section>
        <section class="report-section"><h3>Preparation plan for your next interview</h3><div class="plan-list">${{plan}}</div></section>
        <section class="report-section"><h3>Answer review</h3>${{answerReview}}</section>
        <p class="muted" style="margin-top:16px">See how your scores change day by day and week by week in <a href="/progress?job=${{encodeURIComponent(session?.job?.job_id || '')}}" style="color:#93c5fd">Progress Reports</a>.</p>
      `;
      if (session?.session_id) window.InterviewCoding?.renderRating(scorecard, session.session_id);
      statusText.textContent = 'Scorecard ready. Review your transcript and practice again when ready.';
    }}
    startBtn.addEventListener('click', startInterview);
    stopBtn.addEventListener('click', () => finishInterview());
    speakBtn.addEventListener('click', () => session && speak(session.questions[activeIndex].question, session.questions[activeIndex].id));
    recordBtn.addEventListener('click', recordAnswer);
    saveBtn.addEventListener('click', () => saveAnswer(true));
    clearBtn.addEventListener('click', () => {{
      if (session?.questions?.[activeIndex]?.answer_mode === 'code') codeEditor.value = '';
      else {{ answer.value = ''; recognitionBase = ''; }}
    }});
    codeEditor.addEventListener('keydown', (event) => {{
      if (event.key !== 'Tab') return;
      event.preventDefault();
      const start = codeEditor.selectionStart;
      const end = codeEditor.selectionEnd;
      codeEditor.setRangeText('  ', start, end, 'end');
    }});
    cameraBtn.addEventListener('click', enableCamera);
    function stopAccentPreview() {{
      previewGeneration += 1;
      if (previewAudio) previewAudio.pause();
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewAudio = null;
      previewUrl = null;
      window.speechSynthesis?.cancel();
    }}
    function selectedAccent() {{
      return accentCatalog?.accents.find((item) => item.region === region.value);
    }}
    function updateAccentAvailability() {{
      const selected = selectedAccent();
      if (!selected || region.disabled) return;
      const browserVoice = preferredVoice(selected);
      const available = accentCatalog.tts_provider === 'azure' || browserVoice;
      previewAccent.disabled = !available;
      voiceAvailability.textContent = accentCatalog.tts_provider === 'azure'
        ? `${{selected.label}} · Sarah · Neural voice configured`
        : browserVoice ? `${{selected.label}} · ${{browserVoice.name}}`
        : `${{selected.label}} female voice unavailable on this device. Azure Speech is required for all six regional voices.`;
    }}
    async function loadAccentCatalog() {{
      try {{
        const response = await fetch('/api/mock-interview/accents');
        if (!response.ok) throw new Error('Unable to load regional voices.');
        accentCatalog = await response.json();
        await waitForVoices();
        updateAccentAvailability();
      }} catch (error) {{ voiceAvailability.textContent = error.message; }}
    }}
    previewAccent.addEventListener('click', async () => {{
      stopAccentPreview();
      const generation = previewGeneration;
      const selected = selectedAccent();
      if (!selected || region.disabled) return;
      previewAccent.disabled = true;
      voiceAvailability.textContent = `Preparing ${{selected.label}} preview...`;
      try {{
        if (accentCatalog.tts_provider === 'azure') {{
          const response = await fetch('/api/mock-interview/speech/preview', {{
            method: 'POST', headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{region: selected.region}})
          }});
          if (!response.ok) throw new Error('Regional voice preview unavailable. Please retry.');
          const audio = await response.blob();
          if (generation !== previewGeneration) return;
          previewUrl = URL.createObjectURL(audio);
          previewAudio = new Audio(previewUrl);
          previewAudio.addEventListener('ended', () => {{
            if (generation === previewGeneration) stopAccentPreview();
          }}, {{once: true}});
          await previewAudio.play();
        }} else {{
          const voice = preferredVoice(selected);
          if (!voice) throw new Error('No matching regional female voice is installed.');
          const utterance = new SpeechSynthesisUtterance(accentCatalog.preview_text);
          utterance.voice = voice;
          utterance.lang = selected.lang;
          utterance.rate = 0.92;
          window.speechSynthesis.speak(utterance);
        }}
        if (generation === previewGeneration) updateAccentAvailability();
      }} catch (error) {{
        if (generation === previewGeneration) voiceAvailability.textContent = error.message;
      }} finally {{
        if (generation === previewGeneration && !region.disabled) previewAccent.disabled = false;
      }}
    }});
    region.addEventListener('change', () => {{
      stopAccentPreview();
      accentLabel.textContent = region.options[region.selectedIndex].text;
      updateAccentAvailability();
    }});
    window.speechSynthesis?.addEventListener('voiceschanged', updateAccentAvailability);
    window.addEventListener('pagehide', stopAccentPreview);
    loadAccentCatalog();
    renderTranscript();
    loadQuestions();
    loadHistory();
  </script>
</body>
</html>"""

def _mock_test_page(user_email: str) -> str:
    from .pages import practice_nav

    page = _MOCK_TEST_PAGE.replace("__PRACTICE_NAV__", practice_nav("mock-test", user_email))
    return page.replace("__USER_EMAIL__", _escape_html(user_email))


_MOCK_TEST_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mock Test - Job Hunting Agent</title>
  <style>
    :root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; --blue:#2563eb; --green:#22c55e; --red:#ef4444; --amber:#f59e0b; --line:rgba(148,163,184,.3); --panel:rgba(13,25,43,.92); --muted:#9fb1cc; }
    * { box-sizing: border-box; }
    body { margin:0; min-height:100vh; color:#eef6ff; background: radial-gradient(circle at 50% 15%, rgba(37,99,235,.32), transparent 36%), linear-gradient(120deg, rgba(5,14,29,.96), rgba(9,22,41,.9)), url('/static/job-search-hero.png'); background-size:cover; background-attachment:fixed; }
    .topbar { width:min(1240px, calc(100% - 32px)); margin:0 auto; padding:14px 0; display:flex; justify-content:space-between; gap:12px; align-items:center; flex-wrap:wrap; }
    .topbar nav { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .topbar a, .topbar button { min-height:36px; border:0; border-radius:7px; padding:8px 13px; font-weight:850; text-decoration:none; cursor:pointer; font-size:14px; }
    .topbar a { background:rgba(255,255,255,.94); color:#152238; }
    .topbar form { margin:0; }
    .topbar button { background:#175cd3; color:#fff; }
    .user-chip { padding:8px 12px; border:1px solid rgba(255,255,255,.28); border-radius:999px; background:rgba(255,255,255,.11); font-size:13px; font-weight:800; }
    main { width:min(1240px, calc(100% - 32px)); margin:4px auto 40px; }
    .shell { border:1px solid var(--line); border-radius:10px; background:rgba(6,16,31,.86); box-shadow:0 30px 90px rgba(0,0,0,.45); overflow:hidden; }
    .shell-top { display:flex; justify-content:space-between; gap:12px; align-items:center; flex-wrap:wrap; min-height:52px; padding:10px 16px; background:#0b1424; border-bottom:1px solid var(--line); }
    .brand { display:flex; align-items:center; gap:10px; font-weight:950; }
    .brand-mark { width:30px; height:30px; border-radius:50%; display:grid; place-items:center; background:#1d4ed8; color:#fff; font-size:13px; }
    .top-stats { display:flex; flex-wrap:wrap; gap:16px; color:#cbd5e1; font-size:13px; font-weight:800; }
    .top-stats strong { color:#fff; font-variant-numeric:tabular-nums; }
    .top-stats .low { color:#fca5a5; }
    .view { padding:18px; }
    .hidden { display:none !important; }
    h1, h2, h3 { margin:0; }
    h2 { font-size:20px; }
    h3 { font-size:15px; color:#dbeafe; }
    p { line-height:1.5; }
    .muted { color:var(--muted); }
    .card { border:1px solid var(--line); border-radius:9px; background:var(--panel); padding:16px; }
    .setup-grid { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(0,1fr); gap:16px; }
    label.field { display:block; font-weight:850; color:#dbeafe; margin:14px 0 6px; font-size:14px; }
    select { width:100%; min-height:42px; border:1px solid rgba(148,163,184,.45); border-radius:7px; padding:9px 11px; font:inherit; color:#eef6ff; background:rgba(15,23,42,.9); }
    .chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; min-height:26px; }
    .chip { display:inline-flex; align-items:center; min-height:24px; padding:3px 9px; border-radius:999px; background:rgba(37,99,235,.18); border:1px solid rgba(96,165,250,.35); color:#bfdbfe; font-size:12px; font-weight:850; }
    .segmented { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
    .segmented button { min-height:58px; border-radius:8px; border:1px solid rgba(148,163,184,.4); background:rgba(15,23,42,.85); color:#e2e8f0; font:inherit; font-weight:850; cursor:pointer; padding:8px; }
    .segmented button small { display:block; color:var(--muted); font-weight:700; font-size:12px; margin-top:2px; }
    .segmented button[aria-pressed="true"] { border-color:#60a5fa; background:rgba(37,99,235,.28); box-shadow:inset 0 0 0 1px #60a5fa; }
    .btn { border:0; border-radius:7px; min-height:42px; padding:10px 15px; font:inherit; font-weight:900; cursor:pointer; text-decoration:none; display:inline-flex; align-items:center; justify-content:center; gap:6px; }
    .btn.primary { background:var(--blue); color:#fff; }
    .btn.ghost { background:rgba(255,255,255,.08); color:#e2e8f0; border:1px solid var(--line); }
    .btn.success { background:#16a34a; color:#fff; }
    .btn.warn { background:var(--amber); color:#111827; }
    .btn:disabled { opacity:.55; cursor:not-allowed; }
    .actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:18px; align-items:center; }
    .rules { margin:10px 0 0; padding-left:18px; color:#cbd5e1; font-size:14px; line-height:1.6; }
    .notice { margin-top:12px; padding:10px 12px; border-radius:8px; background:rgba(245,158,11,.12); border:1px solid rgba(245,158,11,.4); color:#fde68a; font-size:14px; }
    .error { background:rgba(239,68,68,.12); border-color:rgba(239,68,68,.45); color:#fecaca; }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    th, td { text-align:left; padding:9px 8px; border-bottom:1px solid rgba(148,163,184,.18); vertical-align:top; }
    th { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    td button { background:none; border:0; color:#93c5fd; font:inherit; font-weight:850; cursor:pointer; padding:0; }
    .test-grid { display:grid; grid-template-columns:minmax(0,1fr) 290px; gap:16px; }
    .q-meta { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
    .pill { display:inline-flex; min-height:24px; align-items:center; padding:3px 9px; border-radius:999px; font-size:12px; font-weight:900; border:1px solid rgba(96,165,250,.35); background:rgba(37,99,235,.18); color:#bfdbfe; }
    .pill.easy { background:rgba(34,197,94,.15); border-color:rgba(34,197,94,.4); color:#bbf7d0; }
    .pill.medium { background:rgba(245,158,11,.14); border-color:rgba(245,158,11,.4); color:#fde68a; }
    .pill.hard { background:rgba(239,68,68,.14); border-color:rgba(239,68,68,.4); color:#fecaca; }
    .pill.ai { background:rgba(168,85,247,.16); border-color:rgba(168,85,247,.45); color:#e9d5ff; }
    .q-text { margin:14px 0 16px; font-size:18px; line-height:1.5; font-weight:800; white-space:pre-wrap; }
    .q-text code, .q-code { font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .code-block { margin:0 0 16px; padding:12px 14px; border-radius:8px; border:1px solid rgba(148,163,184,.35); background:#050b16; color:#dbeafe; font:13px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space:pre; overflow:auto; max-height:360px; }
    .pill.code { background:rgba(14,165,233,.16); border-color:rgba(14,165,233,.45); color:#bae6fd; }
    .report-q { margin-top:8px; background:none; border:0; color:#93c5fd; font:inherit; font-size:12px; font-weight:800; cursor:pointer; padding:0; }
    .options { display:grid; gap:10px; }
    .option { display:grid; grid-template-columns:34px minmax(0,1fr); gap:10px; align-items:center; width:100%; text-align:left; min-height:52px; padding:10px 12px; border-radius:8px; border:1px solid rgba(148,163,184,.4); background:rgba(15,23,42,.85); color:#e2e8f0; font:inherit; font-size:15px; cursor:pointer; white-space:pre-wrap; }
    .option:hover { border-color:#60a5fa; }
    .option .letter { width:30px; height:30px; border-radius:50%; display:grid; place-items:center; background:rgba(148,163,184,.18); font-weight:900; }
    .option[aria-checked="true"] { border-color:#60a5fa; background:rgba(37,99,235,.28); box-shadow:inset 0 0 0 1px #60a5fa; }
    .option[aria-checked="true"] .letter { background:var(--blue); color:#fff; }
    .q-nav { display:flex; flex-wrap:wrap; justify-content:space-between; gap:10px; margin-top:18px; }
    .palette { display:grid; grid-template-columns:repeat(5,1fr); gap:7px; margin-top:12px; }
    .palette button { min-height:38px; border-radius:7px; border:1px solid rgba(148,163,184,.4); background:rgba(15,23,42,.85); color:#e2e8f0; font:inherit; font-weight:900; cursor:pointer; position:relative; }
    .palette button.answered { background:rgba(34,197,94,.22); border-color:rgba(34,197,94,.6); }
    .palette button.marked::after { content:""; position:absolute; top:4px; right:4px; width:7px; height:7px; border-radius:50%; background:var(--amber); }
    .palette button.current { box-shadow:0 0 0 2px #60a5fa; }
    .legend { display:grid; gap:6px; margin-top:14px; font-size:13px; color:#cbd5e1; }
    .legend span::before { content:""; display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:7px; vertical-align:-1px; background:rgba(15,23,42,.85); border:1px solid rgba(148,163,184,.4); }
    .legend .l-answered::before { background:rgba(34,197,94,.4); border-color:rgba(34,197,94,.7); }
    .legend .l-marked::before { background:var(--amber); border-color:var(--amber); border-radius:50%; }
    .kbd { font-size:12px; color:var(--muted); margin-top:12px; line-height:1.5; }
    .result-head { display:grid; grid-template-columns:200px minmax(0,1fr); gap:20px; align-items:center; }
    .ring { width:180px; height:180px; border-radius:50%; display:grid; place-items:center; background:conic-gradient(var(--ring-color, var(--blue)) calc(var(--pct) * 1%), rgba(148,163,184,.18) 0); }
    .ring-inner { width:142px; height:142px; border-radius:50%; background:#0b1424; display:grid; place-items:center; text-align:center; }
    .ring-inner strong { display:block; font-size:34px; font-variant-numeric:tabular-nums; }
    .ring-inner span { color:var(--muted); font-size:13px; font-weight:800; }
    .verdict { margin-top:10px; padding:12px 14px; border-radius:9px; border:1px solid; font-weight:800; }
    .verdict.ready { background:rgba(34,197,94,.12); border-color:rgba(34,197,94,.45); color:#bbf7d0; }
    .verdict.almost { background:rgba(245,158,11,.12); border-color:rgba(245,158,11,.45); color:#fde68a; }
    .verdict.prepare { background:rgba(239,68,68,.12); border-color:rgba(239,68,68,.45); color:#fecaca; }
    .verdict small { display:block; margin-top:4px; font-weight:650; color:#e2e8f0; }
    .stats { display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:10px; margin-top:16px; }
    .stat { border:1px solid var(--line); border-radius:8px; padding:12px; background:rgba(15,23,42,.7); }
    .stat span { display:block; color:var(--muted); font-size:12px; font-weight:850; text-transform:uppercase; letter-spacing:.04em; }
    .stat strong { display:block; margin-top:4px; font-size:22px; font-variant-numeric:tabular-nums; }
    .result-grid { display:grid; grid-template-columns:minmax(0,1.3fr) minmax(0,1fr); gap:16px; margin-top:16px; }
    .bar-row { margin-top:12px; }
    .bar-row .bar-label { display:flex; justify-content:space-between; gap:8px; font-size:14px; font-weight:800; }
    .bar { height:9px; margin-top:6px; border-radius:999px; background:rgba(148,163,184,.18); overflow:hidden; }
    .bar i { display:block; height:100%; border-radius:inherit; background:var(--blue); }
    .bar i.strong { background:var(--green); }
    .bar i.developing { background:var(--amber); }
    .bar i.weak { background:var(--red); }
    .tip { margin:6px 0 0; color:#cbd5e1; font-size:13px; line-height:1.45; }
    ul.plain { margin:8px 0 0; padding-left:18px; line-height:1.6; color:#e2e8f0; font-size:14px; }
    .filters { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
    .filters button { min-height:32px; padding:6px 11px; border-radius:999px; border:1px solid var(--line); background:rgba(15,23,42,.85); color:#e2e8f0; font:inherit; font-size:13px; font-weight:850; cursor:pointer; }
    .filters button[aria-pressed="true"] { background:rgba(37,99,235,.3); border-color:#60a5fa; }
    .review-item { margin-top:12px; padding:14px; border-radius:9px; border:1px solid var(--line); background:rgba(15,23,42,.7); }
    .review-item.correct { border-left:4px solid var(--green); }
    .review-item.incorrect { border-left:4px solid var(--red); }
    .review-item.unanswered { border-left:4px solid var(--amber); }
    .review-q { margin:10px 0; font-weight:800; white-space:pre-wrap; line-height:1.5; }
    .review-opt { padding:7px 10px; margin-top:6px; border-radius:7px; border:1px solid rgba(148,163,184,.25); font-size:14px; white-space:pre-wrap; }
    .review-opt.right { border-color:rgba(34,197,94,.6); background:rgba(34,197,94,.14); }
    .review-opt.wrong { border-color:rgba(239,68,68,.6); background:rgba(239,68,68,.14); }
    .review-opt b { margin-right:6px; }
    .explain { margin:10px 0 0; color:#cbd5e1; font-size:14px; line-height:1.5; }
    @media (max-width: 900px) { .setup-grid, .test-grid, .result-grid, .result-head { grid-template-columns:1fr; } .stats { grid-template-columns:repeat(2, minmax(0,1fr)); } .ring { margin:0 auto; } }
    @media (max-width: 520px) { .segmented { grid-template-columns:1fr; } .palette { grid-template-columns:repeat(6,1fr); } .q-text { font-size:16px; } }
  </style>
</head>
<body>
  __PRACTICE_NAV__
  <main>
    <section class="shell">
      <header class="shell-top">
        <div class="brand"><span class="brand-mark">MT</span><span>Mock Test · Job-Specific Assessment</span></div>
        <div class="top-stats" id="top-stats"><span>Multiple-choice questions tailored to your job leads</span></div>
      </header>

      <section id="setup-view" class="view">
        <div class="setup-grid">
          <div class="card">
            <h2>Set up your test</h2>
            <p class="muted">Pick a job lead and the test is built from its required skills, the skills you matched, and its Additional Skills, plus aptitude and reasoning questions used in screening rounds.</p>
            <label class="field" for="job-select">Job lead</label>
            <select id="job-select"><option value="">Loading your job leads…</option></select>
            <div class="chips" id="job-skills" aria-live="polite"></div>
            <label class="field">Test length</label>
            <div class="segmented" id="length-group" role="group" aria-label="Test length">
              <button type="button" data-length="quick" aria-pressed="false">Quick<small>10 questions · ~13 min</small></button>
              <button type="button" data-length="standard" aria-pressed="true">Standard<small>20 questions · ~25 min</small></button>
              <button type="button" data-length="full" aria-pressed="false">Full<small>30 questions · ~38 min</small></button>
            </div>
            <label class="field" for="difficulty-select">Difficulty</label>
            <select id="difficulty-select">
              <option value="mixed">Mixed - matched to your experience (recommended)</option>
              <option value="easy">Mostly easy</option>
              <option value="medium">Mostly medium</option>
              <option value="hard">Mostly hard</option>
            </select>
            <div class="actions">
              <button type="button" class="btn primary" id="start-button">Start Mock Test</button>
              <span class="muted" id="setup-status"></span>
            </div>
            <div id="setup-error" class="notice error hidden" role="alert"></div>
          </div>
          <div class="card">
            <h3>How it works</h3>
            <ul class="rules">
              <li>One correct answer per question; no negative marking.</li>
              <li>The timer runs on the server. The test auto-submits when time is up.</li>
              <li>Move between questions freely and mark any for review.</li>
              <li>Your answers are saved in this browser if the page reloads.</li>
              <li>Answers and explanations are shown only after you submit.</li>
              <li>Each retake prefers questions you have not seen before.</li>
              <li>Technical jobs include code questions: predict the output, spot the bug, estimate complexity. Every code answer is verified by running it.</li>
              <li>The difficulty mix you choose is applied exactly; your daily and weekly trends are in <a href="/progress" style="color:#93c5fd">Progress Reports</a>.</li>
            </ul>
            <h3 style="margin-top:18px">Recent tests</h3>
            <div id="history" class="muted" style="margin-top:8px">No completed tests yet.</div>
          </div>
        </div>
      </section>

      <section id="test-view" class="view hidden">
        <div class="test-grid">
          <div class="card">
            <div class="q-meta" id="q-meta"></div>
            <div class="q-text" id="q-text"></div>
            <pre class="code-block hidden" id="q-code" aria-label="Code for this question"></pre>
            <div class="options" id="q-options" role="radiogroup" aria-labelledby="q-text"></div>
            <div class="q-nav">
              <div class="actions" style="margin:0">
                <button type="button" class="btn ghost" id="prev-button">← Previous</button>
                <button type="button" class="btn ghost" id="mark-button">Mark for review</button>
                <button type="button" class="btn ghost" id="clear-button">Clear answer</button>
              </div>
              <button type="button" class="btn primary" id="next-button">Next →</button>
            </div>
          </div>
          <aside class="card">
            <h3 id="test-title">Questions</h3>
            <p class="muted" id="test-subtitle" style="margin:4px 0 0; font-size:13px"></p>
            <div class="palette" id="palette"></div>
            <div class="legend"><span class="l-answered">Answered</span><span>Not answered</span><span class="l-marked">Marked for review</span></div>
            <div class="actions"><button type="button" class="btn success" id="submit-button" style="width:100%">Submit Test</button></div>
            <p class="kbd">Shortcuts: 1–4 or A–D to answer · ← → to move · M to mark</p>
          </aside>
        </div>
      </section>

      <section id="result-view" class="view hidden">
        <div class="card">
          <div class="result-head">
            <div class="ring" id="score-ring" style="--pct:0"><div class="ring-inner"><div><strong id="score-percent">0%</strong><span id="score-fraction">0/0 correct</span></div></div></div>
            <div>
              <h2 id="result-title">Scorecard</h2>
              <p class="muted" id="result-subtitle" style="margin:6px 0 0"></p>
              <div class="verdict" id="verdict"></div>
            </div>
          </div>
          <div class="stats" id="stats"></div>
        </div>
        <div class="result-grid">
          <div class="card">
            <h3>Topic breakdown</h3>
            <div id="topic-breakdown"></div>
          </div>
          <div class="card">
            <h3>Difficulty breakdown</h3>
            <div id="difficulty-breakdown"></div>
            <h3 style="margin-top:18px">Strengths</h3>
            <ul class="plain" id="strengths"></ul>
            <h3 style="margin-top:18px">Focus next</h3>
            <ul class="plain" id="weak-areas"></ul>
          </div>
        </div>
        <div class="card" style="margin-top:16px">
          <h3>Answer review</h3>
          <div class="filters" id="review-filters">
            <button type="button" data-filter="all" aria-pressed="true">All</button>
            <button type="button" data-filter="incorrect" aria-pressed="false">Incorrect</button>
            <button type="button" data-filter="unanswered" aria-pressed="false">Unanswered</button>
            <button type="button" data-filter="correct" aria-pressed="false">Correct</button>
          </div>
          <div id="review-list"></div>
        </div>
        <div class="actions">
          <button type="button" class="btn primary" id="retake-button">Retake with new questions</button>
          <button type="button" class="btn ghost" id="new-test-button">Choose another job</button>
          <a class="btn ghost" href="/mock-interview">Practise the interview</a>
          <a class="btn ghost" href="/">Back to Dashboard</a>
        </div>
      </section>
    </section>
  </main>
  <script>
    const LETTERS = ['A', 'B', 'C', 'D'];
    const state = { options: null, length: 'standard', test: null, current: 0, answers: {}, marked: {}, seconds: {}, enteredAt: 0, deadline: 0, timerId: 0, submitting: false, filter: 'all', lastSetup: null };
    const $ = (id) => document.getElementById(id);
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'}[ch]));
    }
    function formatTime(total) {
      const value = Math.max(0, Math.round(total));
      const minutes = Math.floor(value / 60);
      const seconds = String(value % 60).padStart(2, '0');
      return `${minutes}:${seconds}`;
    }
    function storageKey(id) { return `mock-test-${id}`; }
    function saveProgress() {
      if (!state.test) return;
      try { localStorage.setItem(storageKey(state.test.test_id), JSON.stringify({ answers: state.answers, marked: state.marked, seconds: state.seconds, current: state.current })); } catch (error) { /* storage unavailable */ }
    }
    function loadProgress(id) {
      try { return JSON.parse(localStorage.getItem(storageKey(id)) || 'null'); } catch (error) { return null; }
    }
    function clearProgress(id) { try { localStorage.removeItem(storageKey(id)); } catch (error) { /* ignore */ } }
    async function api(url, options = {}) {
      const response = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...options });
      if (response.status === 401) { window.location.href = '/login'; throw new Error('Please sign in again.'); }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
      return data;
    }
    function show(view) {
      for (const id of ['setup-view', 'test-view', 'result-view']) $(id).classList.toggle('hidden', id !== view);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    function setError(message) {
      $('setup-error').textContent = message || '';
      $('setup-error').classList.toggle('hidden', !message);
    }

    // ---------- setup ----------
    async function loadOptions() {
      const params = new URLSearchParams(window.location.search);
      try {
        state.options = await api('/api/mock-test/options');
      } catch (error) {
        setError(error.message);
        return;
      }
      const select = $('job-select');
      const jobs = state.options.jobs || [];
      const general = state.options.profile.target_roles.length ? `General practice: ${state.options.profile.target_roles.slice(0, 2).join(', ')}` : 'General practice (from your profile)';
      select.innerHTML = `<option value="">${escapeHtml(general)}</option>` + jobs.map((job, index) => {
        const label = `${job.title}${job.company ? ' · ' + job.company : ''}${job.match_score ? ' · ' + job.match_score + '% match' : ''}`;
        return `<option value="${index}">${escapeHtml(label)}</option>`;
      }).join('');
      if (!jobs.length) $('setup-status').textContent = 'Run the agent from the dashboard to get job-specific tests.';
      const wanted = params.get('job');
      if (wanted) {
        const index = jobs.findIndex((job) => job.job_id === wanted);
        if (index >= 0) select.value = String(index);
      }
      renderJobSkills();
      loadHistory();
      const testId = params.get('test');
      if (testId) openTest(Number(testId));
    }
    function selectedJob() {
      const value = $('job-select').value;
      return value === '' ? null : (state.options.jobs || [])[Number(value)];
    }
    function renderJobSkills() {
      const job = selectedJob();
      const skills = job ? job.skills : (state.options?.profile.skills || []);
      $('job-skills').innerHTML = skills.length
        ? skills.map((skill) => `<span class="chip">${escapeHtml(skill)}</span>`).join('')
        : '<span class="muted" style="font-size:13px">Topics are chosen from the job title and description.</span>';
    }
    async function loadHistory() {
      try {
        const data = await api('/api/mock-test/history');
        const tests = data.tests || [];
        $('history').innerHTML = tests.length ? `<table><thead><tr><th>Job</th><th>Score</th><th>Result</th></tr></thead><tbody>${tests.map((test) => `
          <tr><td><button type="button" data-test="${test.test_id}">${escapeHtml(test.job_title)}</button><br><span class="muted" style="font-size:12px">${escapeHtml(test.company || '')} ${escapeHtml((test.completed_at || '').slice(0, 10))}</span></td>
          <td><strong>${escapeHtml(Math.round(test.percent || 0))}%</strong><br><span class="muted" style="font-size:12px">${escapeHtml(test.score)}/${escapeHtml(test.total)}</span></td>
          <td>${escapeHtml(test.grade)}<br><span class="muted" style="font-size:12px">${escapeHtml(test.readiness)}</span></td></tr>`).join('')}</tbody></table>` : 'No completed tests yet.';
        $('history').querySelectorAll('button[data-test]').forEach((button) => button.addEventListener('click', () => openTest(Number(button.dataset.test))));
      } catch (error) {
        $('history').textContent = 'History is unavailable right now.';
      }
    }
    async function startTest(setup) {
      setError('');
      $('start-button').disabled = true;
      $('setup-status').textContent = 'Building your test…';
      try {
        const test = await api('/api/mock-test/start', { method: 'POST', body: JSON.stringify(setup) });
        state.lastSetup = setup;
        beginTest(test);
      } catch (error) {
        setError(error.message);
      } finally {
        $('start-button').disabled = false;
        $('setup-status').textContent = '';
      }
    }
    async function openTest(testId) {
      try {
        const test = await api(`/api/mock-test/${encodeURIComponent(testId)}`);
        if (test.status === 'completed') renderResult(test);
        else beginTest(test);
      } catch (error) {
        setError(error.message);
      }
    }

    // ---------- test runner ----------
    function beginTest(test) {
      state.test = test;
      state.submitting = false;
      const saved = loadProgress(test.test_id) || {};
      state.answers = saved.answers || {};
      state.marked = saved.marked || {};
      state.seconds = saved.seconds || {};
      state.current = Math.min(saved.current || 0, test.questions.length - 1);
      const remaining = typeof test.remaining_seconds === 'number' ? test.remaining_seconds : test.time_limit_seconds;
      state.deadline = Date.now() + remaining * 1000;
      $('test-title').textContent = test.job_title;
      const mix = test.difficulty_mix || {};
      const mixText = ` · ${mix.easy || 0} easy / ${mix.medium || 0} medium / ${mix.hard || 0} hard`;
      const codeText = test.coding_count ? ` · ${test.coding_count} code questions` : '';
      $('test-subtitle').textContent = `${test.company ? test.company + ' · ' : ''}${test.questions.length} questions${mixText}${codeText} · ${test.topics.slice(0, 4).join(', ')}`;
      history.replaceState(null, '', `/mock-test?test=${encodeURIComponent(test.test_id)}`);
      show('test-view');
      renderQuestion();
      clearInterval(state.timerId);
      state.timerId = setInterval(tick, 1000);
      tick();
    }
    function updateStats() {
      if (!state.test) return;
      const left = (state.deadline - Date.now()) / 1000;
      const answered = Object.values(state.answers).filter((value) => value !== null && value !== undefined).length;
      $('top-stats').innerHTML = `<span>Time left <strong class="${left < 60 ? 'low' : ''}">${formatTime(left)}</strong></span><span>Answered <strong>${answered}/${state.test.questions.length}</strong></span><span>Marked <strong>${Object.values(state.marked).filter(Boolean).length}</strong></span>`;
      return left;
    }
    function tick() {
      const left = updateStats();
      if (left !== undefined && left <= 0 && !state.submitting) submitTest(true);
    }
    function recordTime() {
      if (!state.test || !state.enteredAt) return;
      const id = state.test.questions[state.current].id;
      state.seconds[id] = (state.seconds[id] || 0) + (Date.now() - state.enteredAt) / 1000;
      state.enteredAt = Date.now();
    }
    function goTo(index) {
      recordTime();
      state.current = Math.max(0, Math.min(index, state.test.questions.length - 1));
      saveProgress();
      renderQuestion();
    }
    function renderQuestion() {
      const question = state.test.questions[state.current];
      state.enteredAt = Date.now();
      $('q-meta').innerHTML = `<span class="pill">Question ${question.number} of ${state.test.questions.length}</span><span class="pill">${escapeHtml(question.topic_label)}</span><span class="pill ${escapeHtml(question.difficulty)}">${escapeHtml(question.difficulty)}</span>${question.kind === 'code' ? '<span class="pill code">Code</span>' : ''}${question.source === 'ai_generated' ? '<span class="pill ai">AI-generated</span>' : ''}`;
      $('q-text').textContent = question.question;
      $('q-code').textContent = question.code || '';
      $('q-code').classList.toggle('hidden', !question.code);
      const chosen = state.answers[question.id];
      $('q-options').innerHTML = question.options.map((option, index) => `
        <button type="button" class="option" role="radio" aria-checked="${chosen === index}" data-index="${index}"><span class="letter">${LETTERS[index]}</span><span>${escapeHtml(option)}</span></button>`).join('');
      $('q-options').querySelectorAll('.option').forEach((button) => button.addEventListener('click', () => choose(Number(button.dataset.index))));
      $('prev-button').disabled = state.current === 0;
      $('next-button').textContent = state.current === state.test.questions.length - 1 ? 'Review & submit' : 'Next →';
      $('mark-button').textContent = state.marked[question.id] ? 'Unmark review' : 'Mark for review';
      renderPalette();
    }
    function renderPalette() {
      $('palette').innerHTML = state.test.questions.map((question, index) => {
        const classes = [
          state.answers[question.id] !== undefined && state.answers[question.id] !== null ? 'answered' : '',
          state.marked[question.id] ? 'marked' : '',
          index === state.current ? 'current' : '',
        ].filter(Boolean).join(' ');
        return `<button type="button" class="${classes}" data-index="${index}" aria-label="Question ${index + 1}">${index + 1}</button>`;
      }).join('');
      $('palette').querySelectorAll('button').forEach((button) => button.addEventListener('click', () => goTo(Number(button.dataset.index))));
      updateStats();
    }
    function choose(index) {
      const question = state.test.questions[state.current];
      state.answers[question.id] = index;
      saveProgress();
      renderQuestion();
    }
    async function submitTest(auto = false) {
      if (state.submitting || !state.test) return;
      const unanswered = state.test.questions.filter((question) => state.answers[question.id] === undefined || state.answers[question.id] === null).length;
      if (!auto && unanswered && !window.confirm(`You have ${unanswered} unanswered question${unanswered === 1 ? '' : 's'}. Submit anyway?`)) return;
      state.submitting = true;
      recordTime();
      clearInterval(state.timerId);
      $('submit-button').disabled = true;
      $('submit-button').textContent = auto ? 'Time is up — submitting…' : 'Submitting…';
      try {
        const result = await api('/api/mock-test/submit', { method: 'POST', body: JSON.stringify({ test_id: state.test.test_id, answers: state.answers, question_seconds: state.seconds }) });
        clearProgress(state.test.test_id);
        renderResult(result);
        loadHistory();
      } catch (error) {
        state.submitting = false;
        $('submit-button').disabled = false;
        $('submit-button').textContent = 'Submit Test';
        window.alert(`Could not submit: ${error.message}. Your answers are saved; please try again.`);
        state.timerId = setInterval(tick, 1000);
      }
    }

    // ---------- scorecard ----------
    function renderResult(test) {
      state.test = null;
      clearInterval(state.timerId);
      $('submit-button').disabled = false;
      $('submit-button').textContent = 'Submit Test';
      const card = test.scorecard || {};
      state.resultTestId = test.test_id;
      $('top-stats').innerHTML = `<span>Completed <strong>${escapeHtml((test.completed_at || '').slice(0, 10))}</strong></span><span>Score <strong>${escapeHtml(card.correct || 0)}/${escapeHtml(card.total || 0)}</strong></span>`;
      state.lastSetup = { job_id: test.job_id || '', run_id: test.run_id || 0, length: test.length || 'standard', difficulty: test.difficulty || 'mixed' };
      history.replaceState(null, '', `/mock-test?test=${encodeURIComponent(test.test_id)}`);
      const percent = Number(card.percent || 0);
      const ringColor = percent >= 70 ? 'var(--green)' : percent >= 50 ? 'var(--amber)' : 'var(--red)';
      $('score-ring').style.setProperty('--pct', String(percent));
      $('score-ring').style.setProperty('--ring-color', ringColor);
      $('score-percent').textContent = `${Math.round(percent)}%`;
      $('score-fraction').textContent = `${card.correct || 0}/${card.total || 0} correct`;
      $('result-title').textContent = `${card.grade || 'Scorecard'} · ${test.job_title}`;
      const improvement = card.improvement === null || card.improvement === undefined ? '' : ` · ${card.improvement >= 0 ? '+' : ''}${card.improvement} pts vs your best for this job`;
      $('result-subtitle').textContent = `${test.company ? test.company + ' · ' : ''}${(test.length || '').replace(/^./, (c) => c.toUpperCase())} test · ${test.difficulty} difficulty${improvement}`;
      const readiness = card.readiness || {};
      $('verdict').className = `verdict ${readiness.level || 'almost'}`;
      $('verdict').innerHTML = `${escapeHtml(readiness.label || '')}<small>${escapeHtml(readiness.detail || '')}</small>`;
      const time = card.time || {};
      $('stats').innerHTML = [
        ['Correct', card.correct], ['Incorrect', card.incorrect], ['Unanswered', card.unanswered],
        ['Accuracy', `${Math.round(card.accuracy || 0)}%`],
        ['Time used', `${formatTime(time.elapsed_seconds || 0)} / ${formatTime(time.limit_seconds || 0)}`],
        ...((card.coding || {}).total ? [['Code questions', `${card.coding.correct}/${card.coding.total} correct`]] : []),
      ].map(([label, value]) => `<div class="stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? 0)}</strong></div>`).join('');
      $('topic-breakdown').innerHTML = (card.topic_breakdown || []).map((row) => `
        <div class="bar-row"><div class="bar-label"><span>${escapeHtml(row.label)}</span><span>${escapeHtml(row.correct)}/${escapeHtml(row.total)} · ${escapeHtml(Math.round(row.percent))}%</span></div>
        <div class="bar"><i class="${escapeHtml(row.status)}" style="width:${Number(row.percent) || 0}%"></i></div>
        ${row.status !== 'strong' && row.tip ? `<p class="tip">${escapeHtml(row.tip)}</p>` : ''}</div>`).join('');
      $('difficulty-breakdown').innerHTML = (card.difficulty_breakdown || []).map((row) => `
        <div class="bar-row"><div class="bar-label"><span style="text-transform:capitalize">${escapeHtml(row.difficulty)}</span><span>${escapeHtml(row.correct)}/${escapeHtml(row.total)}</span></div>
        <div class="bar"><i style="width:${Number(row.percent) || 0}%"></i></div></div>`).join('');
      $('strengths').innerHTML = (card.strengths || []).length ? card.strengths.map((item) => `<li>${escapeHtml(item)}</li>`).join('') : '<li class="muted">Score 80% or more in a topic to list it here.</li>';
      $('weak-areas').innerHTML = (card.weak_areas || []).length
        ? card.weak_areas.map((item) => `<li><strong>${escapeHtml(item.label)}</strong> (${escapeHtml(Math.round(item.percent))}%): ${escapeHtml(item.tip)}</li>`).join('')
        : '<li class="muted">No topic below 50%. Keep practising the lowest bars above.</li>';
      if (time.submitted_after_time_limit) $('weak-areas').insertAdjacentHTML('beforeend', '<li>This attempt was submitted after the time limit. Practise pacing: about one minute per question.</li>');
      state.review = card.review || [];
      state.filter = 'all';
      document.querySelectorAll('#review-filters button').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.filter === 'all')));
      renderReview();
      show('result-view');
    }
    function renderReview() {
      const items = state.review.filter((item) => state.filter === 'all' || item.status === state.filter);
      $('review-list').innerHTML = items.length ? items.map((item) => `
        <div class="review-item ${escapeHtml(item.status)}">
          <div class="q-meta"><span class="pill">Q${escapeHtml(item.number)}</span><span class="pill">${escapeHtml(item.topic_label)}</span><span class="pill ${escapeHtml(item.difficulty)}">${escapeHtml(item.difficulty)}</span>${item.source === 'ai_generated' ? '<span class="pill ai">AI-generated</span>' : ''}<span class="pill">${item.status === 'correct' ? 'Correct' : item.status === 'incorrect' ? 'Incorrect' : 'Not answered'}</span></div>
          <div class="review-q">${escapeHtml(item.question)}</div>
          ${item.code ? `<pre class="code-block">${escapeHtml(item.code)}</pre>` : ''}
          ${item.options.map((option, index) => {
            const cls = index === item.correct_index ? 'right' : index === item.selected_index ? 'wrong' : '';
            const tag = index === item.correct_index ? ' ✓ Correct answer' : index === item.selected_index ? ' ✗ Your answer' : '';
            return `<div class="review-opt ${cls}"><b>${LETTERS[index]}.</b>${escapeHtml(option)}<strong>${tag}</strong></div>`;
          }).join('')}
          ${item.explanation ? `<p class="explain">${escapeHtml(item.explanation)}</p>` : ''}
          <button type="button" class="report-q" data-question="${escapeHtml(item.id)}">Report a problem with this question</button>
        </div>`).join('') : '<p class="muted">Nothing to show for this filter.</p>';
      $('review-list').querySelectorAll('.report-q').forEach((button) => button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          await api('/api/mock-test/report-question', { method: 'POST', body: JSON.stringify({ test_id: state.resultTestId, question_id: button.dataset.question, reason: 'wrong_or_unclear' }) });
          button.textContent = 'Reported - thank you. A reviewer will check this question.';
        } catch (error) {
          button.disabled = false;
          button.textContent = error.message;
        }
      }));
    }

    // ---------- events ----------
    $('job-select').addEventListener('change', renderJobSkills);
    document.querySelectorAll('#length-group button').forEach((button) => button.addEventListener('click', () => {
      state.length = button.dataset.length;
      document.querySelectorAll('#length-group button').forEach((other) => other.setAttribute('aria-pressed', String(other === button)));
    }));
    $('start-button').addEventListener('click', () => {
      const job = selectedJob();
      startTest({ job_id: job ? job.job_id : '', run_id: job ? job.run_id : 0, length: state.length, difficulty: $('difficulty-select').value });
    });
    $('prev-button').addEventListener('click', () => goTo(state.current - 1));
    $('next-button').addEventListener('click', () => {
      if (state.current === state.test.questions.length - 1) submitTest(false); else goTo(state.current + 1);
    });
    $('mark-button').addEventListener('click', () => {
      const id = state.test.questions[state.current].id;
      state.marked[id] = !state.marked[id];
      saveProgress();
      renderQuestion();
    });
    $('clear-button').addEventListener('click', () => {
      delete state.answers[state.test.questions[state.current].id];
      saveProgress();
      renderQuestion();
    });
    $('submit-button').addEventListener('click', () => submitTest(false));
    $('retake-button').addEventListener('click', () => startTest(state.lastSetup || { job_id: '', run_id: 0, length: 'standard', difficulty: 'mixed' }));
    $('new-test-button').addEventListener('click', () => { history.replaceState(null, '', '/mock-test'); show('setup-view'); });
    document.querySelectorAll('#review-filters button').forEach((button) => button.addEventListener('click', () => {
      state.filter = button.dataset.filter;
      document.querySelectorAll('#review-filters button').forEach((other) => other.setAttribute('aria-pressed', String(other === button)));
      renderReview();
    }));
    document.addEventListener('keydown', (event) => {
      if (!state.test || $('test-view').classList.contains('hidden') || event.target.tagName === 'SELECT' || event.ctrlKey || event.metaKey || event.altKey) return;
      const key = event.key.toLowerCase();
      const index = ['1', '2', '3', '4'].indexOf(key) >= 0 ? ['1', '2', '3', '4'].indexOf(key) : ['a', 'b', 'c', 'd'].indexOf(key);
      if (index >= 0 && index < state.test.questions[state.current].options.length) { choose(index); event.preventDefault(); }
      else if (event.key === 'ArrowRight') { goTo(state.current + 1); event.preventDefault(); }
      else if (event.key === 'ArrowLeft') { goTo(state.current - 1); event.preventDefault(); }
      else if (key === 'm') { $('mark-button').click(); event.preventDefault(); }
    });
    window.addEventListener('beforeunload', () => { recordTime(); saveProgress(); });
    loadOptions();
  </script>
</body>
</html>
"""


def _page(user_email: str, profile: dict) -> str:
    """The signed-in dashboard. Layout and styles come from the shared app shell;
    behaviour lives in /static/ui/dashboard.js and uses only the JSON APIs."""
    from .pages import app_shell

    sources = active_job_sources()
    other_sources = [name for name in sources if name not in {"LinkedIn", "Naukri"}]
    body = """
  <section data-view="overview" aria-labelledby="overview-greeting">
    <div class="hero-band">
      <div class="ring" id="overview-ring" role="img" aria-label="No ATS score yet"><span>–<small>No score yet</small></span></div>
      <div>
        <h2 id="overview-greeting">Welcome</h2>
        <p class="lede" id="overview-lede">Upload your resume to get an ATS score, matched job leads, a tailored resume for every lead and recruiter-ready drafts.</p>
        <div class="btn-row"><a class="btn btn-primary" id="overview-primary" href="#run">Upload resume and run</a><a class="btn hidden" id="overview-secondary" href="#jobs">View job leads</a></div>
      </div>
    </div>
    <div class="stat-strip" aria-label="Latest run">
      <div class="stat"><span class="stat-value" id="stat-jobs">–</span><span class="stat-label">Job leads in the latest run</span></div>
      <div class="stat"><span class="stat-value" id="stat-strong">–</span><span class="stat-label">Strong matches (70% and up)</span></div>
      <div class="stat"><span class="stat-value" id="stat-drafts">–</span><span class="stat-label">Drafts ready</span></div>
      <div class="stat"><span class="stat-value" id="stat-approvals">0</span><span class="stat-label">Emails waiting for approval</span></div>
    </div>
    <div class="split">
      <section class="panel" aria-labelledby="next-title"><div class="panel-head"><h3 id="next-title">Next best actions</h3></div><ul class="action-list" id="next-actions"></ul></section>
      <section class="panel" aria-labelledby="top-title"><div class="panel-head"><h3 id="top-title">Top matches</h3><a class="btn btn-sm btn-quiet" href="#jobs">All leads</a></div><div id="top-matches"></div></section>
    </div>
    <div class="split">
      <section class="panel" aria-labelledby="sources-title">
        <div class="panel-head"><h3 id="sources-title">Job sources</h3></div>
        <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap">
          <p class="stat-value" title="__SOURCE_NAMES__" style="display:flex;align-items:baseline;gap:10px;font-size:20px"><strong>__SOURCE_COUNT__</strong><span>Job sources active</span></p>
          <div class="chips" aria-label="Job sources">
            <span class="chip"><span aria-hidden="true">in</span>&nbsp;LinkedIn</span>
            <span class="chip"><span aria-hidden="true">N</span>&nbsp;Naukri</span>
            <span class="chip" title="__OTHER_SOURCE_NAMES__"><span aria-hidden="true">+</span> __OTHER_SOURCE_COUNT__ more job boards</span>
          </div>
        </div>
        <p class="faint" style="margin-top:12px">__SOURCE_NAMES__</p>
      </section>
      <section class="panel" aria-labelledby="auto-title"><div class="panel-head"><h3 id="auto-title">Daily automation</h3><a class="btn btn-sm btn-quiet" href="#run">Change</a></div><div id="overview-schedule"></div></section>
    </div>
  </section>

  <section data-view="run" hidden aria-label="Run and profile">
    <div class="view-head"><div><h2>Run the agent</h2><p>Your resume and search settings. Run once now, or schedule a daily run that finds fresh leads and drafts automatically.</p></div></div>
    <div class="split-run">
      <form id="agent-form" class="panel" novalidate data-has-resume="__HAS_RESUME__">
        <p class="faint" style="margin-bottom:16px" data-i18n="required-note">Fields marked <span class="req">*</span> are required.</p>
        <fieldset>
          <legend>Resume <span class="req" aria-hidden="true">*</span></legend>
          <label class="dropzone" for="resume">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 15v4a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4"/></svg>
            <strong id="dropzone-title">Drop your resume here or choose a file</strong>
            <span class="faint" id="dropzone-hint">PDF, DOCX, TXT or Markdown</span>
            <input id="resume" name="resume" type="file" accept=".pdf,.docx,.txt,.md" aria-describedby="saved-resume">
          </label>
          <p class="muted" id="saved-resume">__RESUME_STATUS__</p>
        </fieldset>
        <fieldset>
          <legend>Candidate</legend>
          <div class="grid-2">
            <label class="field" for="name"><span class="field-label">Name <span class="req" aria-hidden="true">*</span></span><input id="name" name="name" autocomplete="name" required data-label="Name" value="__NAME__"></label>
            <label class="field" for="phone"><span class="field-label">Phone <span class="req" aria-hidden="true">*</span></span><input id="phone" name="phone" type="tel" autocomplete="tel" inputmode="tel" required data-label="Phone" placeholder="+91 98765 43210" value="__PHONE__"></label>
          </div>
          <label class="field" for="email"><span class="field-label">Email <span class="req" aria-hidden="true">*</span></span><input id="email" name="email" type="email" value="__PROFILE_EMAIL__" readonly></label>
          <div class="grid-2">
            <label class="field" for="linkedin_profile_url">LinkedIn profile URL <span class="field-hint">Optional</span><input id="linkedin_profile_url" name="linkedin_profile_url" type="text" inputmode="url" autocomplete="url" placeholder="https://www.linkedin.com/in/your-name" value="__LINKEDIN_PROFILE_URL__"></label>
            <label class="field" for="naukri_profile_url">Naukri profile URL <span class="field-hint">Optional</span><input id="naukri_profile_url" name="naukri_profile_url" type="text" inputmode="url" autocomplete="url" placeholder="https://www.naukri.com/mnjuser/profile" value="__NAUKRI_PROFILE_URL__"></label>
          </div>
          <p class="faint">These links are added to your recruiter email drafts so recruiters can view your profiles. Your LinkedIn link is also used on the ATS resume if your uploaded resume has no contact details. They are not used to sign in to or search LinkedIn or Naukri; jobs are found from your target roles, skills, locations and experience.</p>
        </fieldset>
        <fieldset>
          <legend>Search</legend>
          <label class="field" for="target_roles"><span class="field-label">Target roles <span class="req" aria-hidden="true">*</span></span> <span class="field-hint">Comma separated, for example Data Engineer, Analytics Engineer</span><textarea id="target_roles" name="target_roles" rows="2" required data-label="Target roles">__TARGET_ROLES__</textarea></label>
          <div class="grid-2">
            <label class="field" for="locations"><span class="field-label">Locations <span class="req" aria-hidden="true">*</span></span><textarea id="locations" name="locations" rows="2" required data-label="Locations">__LOCATIONS__</textarea></label>
            <label class="field" for="skills"><span class="field-label">Skills <span class="req" aria-hidden="true">*</span></span><textarea id="skills" name="skills" rows="2" required data-label="Skills">__SKILLS__</textarea></label>
          </div>
          <div class="grid-3">
            <label class="field" for="experience_years"><span class="field-label">Experience (years) <span class="req" aria-hidden="true">*</span></span><input id="experience_years" name="experience_years" type="number" min="0" max="50" step="0.5" inputmode="decimal" required data-label="Experience (years)" value="__EXPERIENCE_YEARS__"></label>
            <label class="field" for="max_jobs_per_portal"><span class="field-label">Max jobs per source <span class="req" aria-hidden="true">*</span></span><input id="max_jobs_per_portal" name="max_jobs_per_portal" type="number" min="1" max="50" required data-label="Max jobs per source" value="__MAX_JOBS__"></label>
            <label class="field" for="application_mode"><span class="field-label">Application mode <span class="req" aria-hidden="true">*</span></span><select id="application_mode" name="application_mode" required data-label="Application mode">__APPLICATION_OPTIONS__</select></label>
          </div>
          <p class="faint">Enter 0 if you are a fresher. Experience sets portal filters; it never adds experience to your ATS report or resume.</p>
          <label class="field" for="job_description">Job description <span class="field-hint">Optional. Paste one to check keywords, required skills and screening risks.</span><textarea id="job_description" name="job_description" rows="6" placeholder="Paste the target job description">__JOB_DESCRIPTION__</textarea></label>
        </fieldset>
        <fieldset>
          <legend>Daily automation</legend>
          <div class="grid-2">
            <label class="field" for="daily_at"><span class="field-label">Daily time <span class="req" aria-hidden="true">*</span></span> <span class="field-hint">Needed for Schedule Daily Run</span><input id="daily_at" name="daily_at" type="time" data-label="Daily time" value="__DAILY_AT__"></label>
            <p class="faint" style="align-self:end">Schedule Daily Run saves this resume and runs the agent every day at this time in your browser's timezone. Schedules survive server restarts.</p>
          </div>
          <input id="daily_timezone" name="daily_timezone" type="hidden" value="UTC">
        </fieldset>
        <label class="check"><input type="checkbox" id="consent" name="consent" value="true" data-label="Privacy notice consent" __CONSENT_CHECKED__> <span data-i18n="consent">I agree to the <a href="/privacy">privacy notice</a>. My resume is used only to score it, find jobs, tailor resumes and prepare drafts. Recruiter emails are sent only after I approve each one.</span> <span class="req" aria-hidden="true">*</span></label>
        <div class="form-actions">
          <button class="btn btn-primary" id="run-submit" type="submit">Run agent</button>
          <button class="btn" id="schedule-run" type="button">Schedule Daily Run</button>
          <button class="btn btn-quiet" id="stop-scheduler" type="button">Stop Daily Run</button>
        </div>
      </form>
      <div class="sticky-col">
        <section class="panel hidden" id="run-progress" aria-live="polite" aria-labelledby="progress-title">
          <div class="panel-head"><h3 id="progress-title">Run progress</h3></div>
          <ol class="stages" id="run-stages"></ol>
          <p class="muted" id="run-status" style="margin-top:14px"></p>
        </section>
        <section class="panel" aria-labelledby="scheduler-title">
          <div class="panel-head"><h3 id="scheduler-title">Daily automation</h3><span class="badge" id="scheduler-pill">Off</span></div>
          <div id="scheduler-status"></div>
        </section>
        <section class="notice"><span>Nothing is sent without you. In Email mode each recruiter email waits in Approvals: review, edit, approve, and you still have a short undo window. Daily limits stop accidental mass emails.</span></section>
      </div>
    </div>
  </section>

  <section data-view="jobs" hidden aria-label="Job leads">
    <div class="view-head"><div><h2>Job leads</h2><p>Individual postings matched by role, skills and location. Experience is checked when a posting states it; otherwise it is marked unverified for your review.</p></div>
      <div class="segmented" id="layout-toggle" role="group" aria-label="Layout"><button type="button" data-layout="list" aria-pressed="true">List</button><button type="button" data-layout="table" aria-pressed="false">Table</button></div></div>
    <div class="toolbar panel" style="padding:14px 16px">
      <label class="search">Search<input id="filter-text" type="search" placeholder="Title, company, skill or location"></label>
      <label>Source<select id="filter-portal"><option value="">All sources</option></select></label>
      <label>Minimum match <span class="range-value" id="filter-score-value">0%</span><input id="filter-score" type="range" min="0" max="100" step="5" value="0"></label>
      <label>Sort<select id="filter-sort"><option value="match">Best match</option><option value="newest">Newest</option><option value="company">Company A to Z</option></select></label>
    </div>
    <p class="faint" id="jobs-count" aria-live="polite"></p>
    <div id="jobs-list"></div>
    <div class="btn-row" id="jobs-more" style="justify-content:center"></div>
    <div id="portal-links"></div>
  </section>

  <section data-view="resume" hidden aria-label="Resume and ATS">
    <div class="view-head"><div><h2>Resume &amp; ATS</h2><p>How applicant tracking systems read your resume, what to fix first, and the validated ATS-ready resume to download.</p></div></div>
    <div id="resume-body" style="display:grid;gap:22px"></div>
    <section class="panel" aria-labelledby="draft-title"><h3 id="draft-title" style="margin-bottom:12px">Reusable Draft Message</h3><div id="draft-host"></div></section>
  </section>

  <section data-view="approvals" hidden aria-label="Approvals">
    <div class="view-head"><div><h2>Emails waiting for your approval</h2><p id="approvals-summary">Review the recipient and the exact text before anything is sent.</p></div></div>
    <div id="approvals-list" style="display:grid;gap:16px" aria-live="polite"></div>
  </section>

  <dialog class="modal" id="missing-dialog" aria-labelledby="missing-title" aria-describedby="missing-intro">
    <h2 id="missing-title">Fill in the required details</h2>
    <p class="muted" id="missing-intro">The agent can run once these are complete:</p>
    <ul class="plain" id="missing-list"></ul>
    <div class="btn-row" style="justify-content:flex-end;margin-top:18px"><button class="btn btn-primary" id="missing-ok" type="button">Fill in now</button></div>
  </dialog>
  <dialog class="drawer" id="changes-drawer" aria-labelledby="drawer-title">
    <div class="drawer-head"><h2 id="drawer-title" style="font-size:19px">Tailored resume</h2><button class="btn btn-icon btn-quiet" id="drawer-close" type="button" aria-label="Close">×</button></div>
    <div class="drawer-body" id="drawer-body"></div>
  </dialog>
"""
    replacements = {
        "__PROFILE_EMAIL__": profile.get("email") or user_email,
        "__NAME__": profile.get("name", ""),
        "__PHONE__": profile.get("phone", ""),
        "__SOURCE_COUNT__": str(len(sources)),
        "__SOURCE_NAMES__": "Searching: " + ", ".join(sources),
        "__OTHER_SOURCE_COUNT__": str(len(other_sources)),
        "__OTHER_SOURCE_NAMES__": ", ".join(other_sources),
        "__LINKEDIN_PROFILE_URL__": profile.get("linkedin_profile_url", ""),
        "__NAUKRI_PROFILE_URL__": profile.get("naukri_profile_url", ""),
        "__TARGET_ROLES__": profile.get("target_roles", ""),
        "__LOCATIONS__": profile.get("locations", ""),
        "__SKILLS__": profile.get("skills", ""),
        "__EXPERIENCE_YEARS__": str(profile.get("experience_years", 0)),
        "__JOB_DESCRIPTION__": profile.get("job_description", ""),
        "__MAX_JOBS__": str(profile.get("max_jobs_per_portal", 10)),
        "__DAILY_AT__": profile.get("daily_at", ""),
        "__HAS_RESUME__": "true" if profile.get("resume_name") else "false",
        "__RESUME_STATUS__": (
            f"Saved resume: {profile['resume_name']}. Choose a file only to replace it."
            if profile.get("resume_name")
            else "No resume saved yet. Upload one for your first run."
        ),
        "__APPLICATION_OPTIONS__": (
            '<option value="draft">Draft only</option><option value="email" selected>Email recruiters after my approval</option>'
            if profile.get("application_mode") == "email"
            else '<option value="draft" selected>Draft only</option><option value="email">Email recruiters after my approval</option>'
        ),
        "__CONSENT_CHECKED__": "checked" if privacy.has_consent(user_email) else "required",
    }
    for token, value in replacements.items():
        body = body.replace(token, value if token in {"__APPLICATION_OPTIONS__", "__CONSENT_CHECKED__"} else _escape_html(value))
    actions = '<a class="btn btn-sm btn-primary" href="#run">Run agent</a>'
    return app_shell(
        "Overview", user_email, body, active="", scripts=("/static/ui/dashboard.js",),
        is_admin=user_email in ADMIN_EMAILS, actions=actions,
    )
