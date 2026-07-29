from __future__ import annotations

import shutil
import hashlib
import hmac
import base64
import json
import os
import secrets
import smtplib
import threading
import time
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import BackgroundTasks, Cookie, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .agent import JobHuntingAgent
from .config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
from .db import (
    active_schedules,
    consume_valid_otp,
    disable_schedule,
    init_db,
    latest_runs,
    normalize_email,
    record_run,
    save_user_profile,
    save_otp,
    save_schedule,
    schedule_for_user,
    update_schedule_status,
    user_profile,
)
from .models import CandidateProfile
from .storage import StoredObject, download_file, mirror_artifacts, presigned_download_url, upload_file

app = FastAPI(title="Job Hunting Agent")

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
if COOKIE_SECURE and APP_SECRET == "local-dev-change-me":
    raise RuntimeError("Set JOB_AGENT_SECRET_KEY to a long random value before running with secure cookies.")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
init_db()


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
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1)
        self._thread = None
        self.next_run_at = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

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


@app.on_event("startup")
def restore_active_schedule() -> None:
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
        print(f"[job-agent] SES OTP delivery is not configured; OTP for {email}: {otp}")
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


def _ses_client():
    import boto3

    return boto3.client("sesv2", region_name=SES_REGION)


@app.get("/", response_class=HTMLResponse)
def index(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> HTMLResponse:
    user_email = current_user_email(job_agent_session)
    if not user_email:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_page(user_email, _profile_for_user(user_email)))


@app.get("/login", response_class=HTMLResponse)
def login_page(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> HTMLResponse:
    if current_user_email(job_agent_session):
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(_login_page())


@app.post("/api/auth/request-otp")
def request_otp(email: Annotated[str, Form()]) -> dict:
    normalized = normalize_email(email)
    if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    otp = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    save_otp(normalized, _hash_otp(normalized, otp), expires_at)
    sent = _send_otp_email(normalized, otp)
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


@app.post("/api/auth/verify")
def verify_otp(email: Annotated[str, Form()], otp: Annotated[str, Form()]) -> HTMLResponse:
    normalized = normalize_email(email)
    if not consume_valid_otp(normalized, _hash_otp(normalized, otp.strip())):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
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


@app.get("/api/dashboard")
def dashboard(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    runs = [_run_with_payload_id(run) for run in latest_runs(user_email, limit=1)]
    latest_run = runs[0] if runs else None
    scheduler = schedulers.get(user_email)
    scheduler_snapshot = scheduler.snapshot() if scheduler else _persisted_scheduler_snapshot(user_email)
    scheduler_snapshot["history"] = [_run_history_item(latest_run)] if latest_run else []
    return {
        "profile": _profile_for_user(user_email),
        "latest_run": latest_run,
        "scheduler": scheduler_snapshot,
    }


@app.get("/api/runs")
def runs(job_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user_email = require_user(job_agent_session)
    return {"runs": [_run_with_payload_id(run) for run in latest_runs(user_email, limit=1)]}


@app.post("/api/run")
async def run_now(
    background_tasks: BackgroundTasks,
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
    application_mode: Annotated[str, Form()] = "draft",
    max_jobs_per_portal: Annotated[int, Form()] = 10,
    daily_at: Annotated[str, Form()] = "",
    daily_timezone: Annotated[str, Form()] = "UTC",
    start_daily: Annotated[bool, Form()] = False,
) -> dict:
    user_email = require_user(job_agent_session)
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
        application_mode=application_mode,
        max_jobs_per_portal=max_jobs_per_portal,
    ))
    _save_profile(user_email, config, stored_resume)
    result = run_agent(str(stored_resume.local_path), config, trigger="manual", user_email=user_email)
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
    application_mode: Annotated[str, Form()] = "draft",
    max_jobs_per_portal: Annotated[int, Form()] = 10,
    daily_at: Annotated[str, Form()] = "",
    daily_timezone: Annotated[str, Form()] = "UTC",
) -> dict:
    user_email = require_user(job_agent_session)
    if not daily_at:
        raise HTTPException(status_code=400, detail="Daily time is required to schedule the agent.")
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
    return schedulers.stop(user_email)


def run_agent(resume_path: str, config: AppConfig, trigger: str = "manual", user_email: str = "") -> dict:
    report, jobs, results, improved_resume = JobHuntingAgent(config).run(resume_path)
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
        "improved_resume": improved_resume,
        "portal_submission_note": (
            "Portal applications are prepared as drafts or recruiter emails. "
            "Authenticated LinkedIn/Naukri submission remains adapter-gated because those portals can require login, CAPTCHA, OTP, and screening answers."
        ),
    }
    artifact_uris = mirror_artifacts(config.application.data_dir, user_email or config.profile.email or "anonymous", result["generated_at"])
    if artifact_uris:
        result["artifact_uris"] = artifact_uris
    if user_email:
        result["run_id"] = record_run(user_email, result)
    return result


@app.get("/api/runs/{run_id}/improved-resume")
def download_improved_resume(
    run_id: int,
    job_agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
):
    user_email = require_user(job_agent_session)
    run = next((item for item in latest_runs(user_email, limit=20) if int(item.get("id", 0)) == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    payload = run.get("payload") or {}
    improved = payload.get("improved_resume") or {}
    uri = improved.get("docx_uri") or ""
    if uri:
        signed_url = presigned_download_url(uri)
        if signed_url:
            return RedirectResponse(signed_url, status_code=303)
    path = Path(improved.get("docx_path") or "")
    if path.exists() and path.is_file():
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=path.name,
        )
    raise HTTPException(status_code=404, detail="Improved resume artifact is not available for this run.")


def _publish_improved_resume(improved_resume: dict[str, str], user_email: str, generated_at: str) -> dict[str, str]:
    published = dict(improved_resume)
    prefix = f"artifacts/{normalize_email(user_email)}/{generated_at}/improved_resume"
    docx_path = improved_resume.get("docx_path")
    if docx_path:
        published["docx_uri"] = upload_file(docx_path, prefix)
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
    summary = {"drafted": 0, "emailed": 0, "email_failed": 0, "skipped": 0}
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
    payload.setdefault("run_id", run.get("id"))
    return {**run, "payload": payload}


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
) -> AppConfig:
    if application_mode not in {"draft", "email"}:
        raise HTTPException(status_code=400, detail="application_mode must be draft or email.")
    return AppConfig(
        profile=CandidateProfile(
            name=name.strip(),
            email=email.strip(),
            phone=phone.strip(),
            linkedin_profile_url=linkedin_profile_url.strip(),
            naukri_profile_url=naukri_profile_url.strip(),
            target_roles=_split_csv(target_roles),
            locations=_split_csv(locations),
            skills=_split_csv(skills),
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
        ),
        search=SearchConfig(
            max_jobs_per_portal=int(search.get("max_jobs_per_portal", 10)),
            freshness_days=int(search.get("freshness_days", 1)),
            include_remote=bool(search.get("include_remote", True)),
            portals=tuple(search.get("portals", ("linkedin", "naukri"))),
        ),
        application=ApplicationConfig(
            mode=application.get("mode", "draft"),
            cover_letter_tone=application.get("cover_letter_tone", "concise"),
            data_dir=application.get("data_dir", str(DATA_DIR)),
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


def _login_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign In - Job Hunting Agent</title>
  <style>
    :root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #142033; }
    * { box-sizing: border-box; }
    body { min-height: 100vh; margin: 0; display: grid; place-items: center; background: linear-gradient(90deg, rgba(9, 24, 47, 0.88), rgba(9, 24, 47, 0.58)), url('/static/job-search-hero.png'); background-size: cover; background-position: center; }
    .shell { width: min(960px, calc(100% - 36px)); display: grid; grid-template-columns: minmax(260px, 1fr) 420px; gap: 28px; align-items: center; }
    .copy { color: #ffffff; }
    .eyebrow { display: inline-flex; padding: 7px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,.35); background: rgba(255,255,255,.14); font-size: 13px; font-weight: 800; }
    h1 { margin: 18px 0 12px; font-size: clamp(34px, 6vw, 60px); line-height: 1; letter-spacing: 0; }
    p { color: rgba(255,255,255,.82); line-height: 1.6; }
    .card { border-radius: 8px; border: 1px solid rgba(255,255,255,.5); background: rgba(255,255,255,.94); padding: 24px; box-shadow: 0 24px 70px rgba(0,0,0,.28); backdrop-filter: blur(18px); }
    .card h2 { margin: 0 0 8px; font-size: 24px; }
    label { display: block; margin: 14px 0 6px; color: #344054; font-size: 13px; font-weight: 800; }
    input { width: 100%; min-height: 44px; border: 1px solid #c9d4e5; border-radius: 7px; padding: 10px 12px; font: inherit; }
    button { width: 100%; min-height: 44px; margin-top: 14px; border: 0; border-radius: 7px; color: #ffffff; background: #175cd3; font-weight: 900; cursor: pointer; }
    .muted { color: #667085; font-size: 13px; line-height: 1.5; }
    .status { min-height: 20px; color: #087443; font-size: 13px; font-weight: 750; }
    @media (max-width: 800px) { .shell { grid-template-columns: 1fr; padding: 28px 0; } }
  </style>
</head>
<body>
  <main class="shell">
    <section class="copy">
      <div class="eyebrow">Secure client workspace</div>
      <h1>Job Hunting Agent</h1>
      <p>Sign in with an email OTP to access resume scoring, job discovery, recruiter draft templates, and daily run history.</p>
    </section>
    <section class="card">
      <h2>Email OTP Sign In</h2>
      <p class="muted">Enter your email to receive a one-time sign-in code.</p>
      <form id="request-form">
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="email" required>
        <button type="submit">Send OTP</button>
      </form>
      <form id="verify-form" method="post" action="/api/auth/verify">
        <input id="verify-email" name="email" type="hidden">
        <label for="otp">OTP</label>
        <input id="otp" name="otp" inputmode="numeric" autocomplete="one-time-code" placeholder="6-digit code" required>
        <button type="submit">Verify and Continue</button>
      </form>
      <p id="status" class="status"></p>
    </section>
  </main>
  <script>
    const requestForm = document.getElementById('request-form');
    const verifyEmail = document.getElementById('verify-email');
    const status = document.getElementById('status');
    requestForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = new FormData(requestForm);
      const response = await fetch('/api/auth/request-otp', { method: 'POST', body: data });
      const payload = await response.json();
      if (!response.ok) {
        status.textContent = payload.detail || 'Unable to send OTP.';
        status.style.color = '#b42318';
        return;
      }
      verifyEmail.value = payload.email;
      status.style.color = '#087443';
      status.textContent = payload.dev_otp
        ? `OTP generated for local testing: ${payload.dev_otp}`
        : `OTP sent to ${payload.email}.`;
    });
  </script>
</body>
</html>"""


def _page(user_email: str, profile: dict) -> str:
    page = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Hunting Agent</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --ink: #142033;
      --muted: #667085;
      --line: #d8e0ec;
      --panel: #ffffff;
      --page: #f3f6fa;
      --blue: #175cd3;
      --green: #087443;
      --gold: #a15c07;
      --shadow: 0 18px 45px rgba(29, 41, 57, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        linear-gradient(180deg, rgba(245, 248, 252, 0.82) 0%, rgba(232, 239, 248, 0.9) 42%, rgba(247, 250, 252, 0.96) 100%),
        url('/static/job-search-hero.png');
      background-attachment: fixed;
      background-position: center top;
      background-size: cover;
      color: var(--ink);
    }
    body::before {
      content: "";
      position: fixed;
      inset: 300px 0 0;
      pointer-events: none;
      background:
        linear-gradient(120deg, rgba(7, 19, 38, 0.08), rgba(255, 255, 255, 0.72) 48%, rgba(23, 92, 211, 0.1)),
        url('/static/job-search-hero.png');
      background-size: cover;
      background-position: center;
      opacity: 0.22;
      filter: saturate(0.9);
    }
    .hero {
      min-height: 330px;
      position: relative;
      display: flex;
      align-items: stretch;
      background-image: linear-gradient(90deg, rgba(9, 24, 47, 0.88) 0%, rgba(9, 24, 47, 0.74) 40%, rgba(9, 24, 47, 0.1) 100%), url('/static/job-search-hero.png');
      background-position: center;
      background-size: cover;
      color: #ffffff;
      border-bottom: 1px solid rgba(255, 255, 255, 0.2);
    }
    .topbar { position: relative; z-index: 3; min-height: 56px; display: flex; justify-content: flex-end; align-items: center; gap: 12px; width: min(1180px, calc(100% - 48px)); margin: 0 auto -56px; color: #ffffff; }
    .user-chip { display: inline-flex; align-items: center; min-height: 34px; padding: 7px 12px; border-radius: 999px; background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.32); font-size: 13px; font-weight: 800; backdrop-filter: blur(12px); }
    .logout-form { margin: 0; padding: 0; border: 0; background: transparent; box-shadow: none; backdrop-filter: none; }
    .logout-form button { min-height: 34px; padding: 7px 12px; border-radius: 999px; background: rgba(255, 255, 255, 0.92); color: #152238; box-shadow: none; font-size: 13px; }
    .hero-content { width: min(1180px, calc(100% - 48px)); margin: 0 auto; padding: 42px 0 34px; display: grid; grid-template-columns: minmax(300px, 620px) 1fr; gap: 28px; align-items: center; }
    .eyebrow { display: inline-flex; align-items: center; gap: 8px; width: fit-content; padding: 7px 10px; border: 1px solid rgba(255, 255, 255, 0.35); border-radius: 999px; background: rgba(255, 255, 255, 0.14); font-size: 13px; font-weight: 750; }
    h1 { margin: 18px 0 12px; max-width: 620px; font-size: clamp(34px, 5vw, 58px); line-height: 1.02; letter-spacing: 0; }
    .hero p { margin: 0; max-width: 620px; color: rgba(255, 255, 255, 0.86); font-size: 16px; line-height: 1.6; }
    .platform-strip { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
    .platform-chip { display: inline-flex; align-items: center; gap: 9px; padding: 9px 12px; border-radius: 999px; background: rgba(255, 255, 255, 0.95); color: #152238; font-size: 13px; font-weight: 800; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16); }
    .platform-mark { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 6px; color: #ffffff; font-size: 11px; font-weight: 900; }
    .platform-mark.linkedin { background: #0a66c2; }
    .platform-mark.naukri { background: #f36f21; }
    .platform-mark.mail { background: #087443; }
    .hero-stats { justify-self: end; display: grid; gap: 12px; min-width: 280px; }
    .stat-card { width: 100%; padding: 16px 18px; border-radius: 8px; background: rgba(255, 255, 255, 0.93); color: #152238; box-shadow: var(--shadow); }
    .stat-card strong { display: block; font-size: 28px; line-height: 1; }
    .stat-card span { display: block; margin-top: 5px; color: #5b6472; font-size: 13px; font-weight: 700; }
    main { width: min(1180px, calc(100% - 48px)); margin: -38px auto 44px; display: grid; grid-template-columns: minmax(340px, 500px) minmax(340px, 1fr); gap: 24px; position: relative; z-index: 2; }
    form, .panel { background: rgba(255, 255, 255, 0.9); border: 1px solid rgba(216, 224, 236, 0.86); border-radius: 8px; box-shadow: 0 22px 60px rgba(22, 34, 51, 0.16); backdrop-filter: blur(18px); }
    form { padding: 8px 20px 20px; }
    .panel { padding: 22px; min-height: 520px; background: linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(244, 248, 253, 0.9) 100%); }
    fieldset { border: 0; padding: 18px 0 2px; margin: 0; border-bottom: 1px solid #edf1f6; }
    fieldset:last-of-type { border-bottom: 0; }
    legend { display: flex; align-items: center; gap: 10px; width: 100%; font-size: 16px; font-weight: 850; margin-bottom: 2px; }
    .section-badge { display: inline-grid; place-items: center; width: 28px; height: 28px; border-radius: 7px; background: #eaf2ff; color: var(--blue); font-size: 13px; font-weight: 900; }
    label { display: block; color: #344054; font-size: 13px; font-weight: 750; margin: 12px 0 6px; }
    input, select, textarea { width: 100%; min-height: 42px; border: 1px solid #c9d4e5; border-radius: 7px; padding: 9px 11px; font: inherit; background: #ffffff; color: var(--ink); outline: none; transition: border-color 140ms ease, box-shadow 140ms ease; }
    input:focus, select:focus, textarea:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(23, 92, 211, 0.12); }
    input[type="file"] { padding: 8px; background: #f8fafc; }
    textarea { min-height: 82px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .checkline { display: flex; gap: 10px; align-items: center; min-height: 42px; margin-top: 30px; padding: 10px 12px; border: 1px solid #d8e0ec; border-radius: 7px; background: #f8fafc; color: #344054; font-size: 13px; font-weight: 750; }
    .checkline input { width: 18px; min-height: 18px; accent-color: var(--blue); }
    .schedule-help { min-height: 42px; margin-top: 30px; padding: 10px 12px; border: 1px solid #d8e0ec; border-radius: 7px; background: #f8fafc; color: #344054; font-size: 13px; font-weight: 750; line-height: 1.35; }
    button { min-height: 44px; border: 0; border-radius: 7px; padding: 10px 15px; font-weight: 850; cursor: pointer; background: var(--blue); color: white; box-shadow: 0 10px 24px rgba(23, 92, 211, 0.24); }
    button.secondary { background: #394150; box-shadow: none; }
    button:hover { filter: brightness(1.04); }
    .actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding-top: 16px; }
    .muted { color: var(--muted); font-size: 13px; line-height: 1.5; }
    .note { margin: 14px 0 0; padding: 12px; border-radius: 7px; background: #fff8eb; border: 1px solid #fedf89; color: #7a4a08; }
    .workflow-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 14px 0 4px; }
    .workflow-card { min-height: 86px; padding: 13px; border-radius: 8px; border: 1px solid rgba(223, 231, 242, 0.9); background: linear-gradient(135deg, rgba(255, 255, 255, 0.96) 0%, rgba(237, 245, 255, 0.94) 100%); box-shadow: 0 12px 30px rgba(29, 41, 57, 0.08); }
    .workflow-card:nth-child(2) { background: linear-gradient(135deg, #ffffff 0%, #ecfdf3 100%); }
    .workflow-card:nth-child(3) { background: linear-gradient(135deg, #ffffff 0%, #fff7ed 100%); }
    .workflow-card strong { display: block; font-size: 13px; margin-top: 9px; }
    .workflow-card span { color: var(--muted); font-size: 12px; font-weight: 700; }
    .workflow-icon { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 8px; color: #ffffff; font-size: 14px; font-weight: 900; background: var(--blue); }
    .workflow-card:nth-child(2) .workflow-icon { background: var(--green); }
    .workflow-card:nth-child(3) .workflow-icon { background: var(--gold); }
    .workspace-header { display: grid; grid-template-columns: minmax(180px, 1fr) minmax(280px, 340px); gap: 16px; align-items: start; margin-bottom: 20px; }
    .results-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
    .results-header h2 { margin: 0; font-size: 26px; letter-spacing: 0; }
    .status-pill { display: inline-flex; align-items: center; min-height: 30px; padding: 6px 10px; border-radius: 999px; background: #ecfdf3; color: var(--green); font-size: 12px; font-weight: 850; white-space: nowrap; }
    .empty-state { display: grid; place-items: center; min-height: 360px; border: 1px dashed #cbd5e1; border-radius: 8px; background: #f8fafc; text-align: center; padding: 24px; }
    .empty-visual { width: 118px; height: 90px; margin-bottom: 14px; border-radius: 8px; background: #ffffff; border: 1px solid #d8e0ec; box-shadow: 0 10px 24px rgba(29, 41, 57, 0.08); position: relative; }
    .empty-visual::before { content: ""; position: absolute; left: 18px; right: 18px; top: 22px; height: 8px; border-radius: 4px; background: #175cd3; box-shadow: 0 18px 0 #d8e0ec, 0 36px 0 #d8e0ec; }
    .scheduler-panel { padding: 13px; border: 1px solid #d8e2f0; border-radius: 8px; background: linear-gradient(145deg, #f8fbff, #eef4fb); box-shadow: 0 10px 26px rgba(29, 41, 57, 0.08); }
    .scheduler-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
    .scheduler-panel-head h3 { margin: 0; font-size: 14px; }
    .scheduler-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
    .scheduler-card { padding: 8px; border: 1px solid #dfe6f0; border-radius: 6px; background: rgba(255, 255, 255, 0.82); }
    .scheduler-card strong { display: block; font-size: 10px; color: #5b6472; text-transform: uppercase; }
    .scheduler-card span { display: block; margin-top: 3px; font-size: 12px; font-weight: 800; color: var(--ink); overflow-wrap: anywhere; }
    .status-pill.off { background: #f2f4f7; color: #5b6472; }
    .status-pill.error { background: #fef3f2; color: #b42318; }
    .metric { display: inline-flex; align-items: baseline; gap: 7px; padding: 10px 12px; border: 1px solid #dfe4ee; border-radius: 7px; margin: 0 8px 8px 0; background: #fbfcfe; }
    .metric strong { font-size: 26px; }
    .download-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 8px 0 12px; }
    .download-button { display: inline-flex; align-items: center; justify-content: center; min-height: 38px; padding: 9px 12px; border-radius: 7px; background: var(--blue); color: #ffffff; text-decoration: none; font-weight: 850; box-shadow: 0 10px 24px rgba(23, 92, 211, 0.2); }
    .download-button:hover { filter: brightness(1.04); }
    .history-list { grid-column: 1 / -1; margin: 2px 0 0; padding: 8px; list-style: none; border: 1px solid #dfe6f0; border-radius: 6px; background: rgba(255, 255, 255, 0.82); }
    .history-list li { margin: 0; font-size: 11px; line-height: 1.4; }
    .result-section { margin-top: 18px; padding: 16px; border: 1px solid rgba(225, 232, 242, 0.92); border-radius: 8px; background: rgba(255, 255, 255, 0.84); box-shadow: 0 12px 32px rgba(29, 41, 57, 0.07); }
    .result-section h3 { margin: 0 0 12px; font-size: 18px; }
    .result-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .insight-list { margin: 0; padding-left: 18px; }
    .table-wrap { overflow-x: auto; border-radius: 8px; }
    .draft-grid { display: grid; gap: 12px; }
    .draft-card { border: 1px solid #dfe7f2; border-radius: 8px; background: #ffffff; overflow: hidden; }
    .draft-card-header { display: flex; justify-content: space-between; gap: 12px; padding: 12px; background: #f8fafc; border-bottom: 1px solid #e6eaf1; }
    .draft-card-header strong { display: block; }
    .draft-card-header span { color: var(--muted); font-size: 12px; }
    .draft-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .copy-draft { min-height: 34px; padding: 7px 10px; box-shadow: none; font-size: 12px; }
    .draft-message { width: 100%; min-height: 180px; border: 0; border-radius: 0; border-top: 1px solid #eef2f7; background: #fbfcfe; font-size: 13px; line-height: 1.5; }
    ul { padding-left: 20px; }
    li { margin: 6px 0; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; overflow: hidden; border: 1px solid #e6eaf1; border-radius: 8px; }
    th, td { text-align: left; padding: 11px 9px; border-bottom: 1px solid #e6eaf1; vertical-align: top; }
    th { background: #f8fafc; color: #344054; font-size: 12px; text-transform: uppercase; }
    td a { color: var(--blue); font-weight: 800; }
    @media (max-width: 900px) {
      .hero { min-height: 380px; }
      .hero-content { width: min(100% - 32px, 720px); grid-template-columns: 1fr; padding: 28px 0 70px; }
      .hero-stats { justify-self: stretch; grid-template-columns: 1fr 1fr; min-width: 0; }
      main { width: min(100% - 32px, 720px); grid-template-columns: 1fr; margin-top: -42px; }
      .workspace-header { grid-template-columns: 1fr; }
      .row { grid-template-columns: 1fr; }
      .checkline { margin-top: 12px; }
      h1 { font-size: 38px; }
    }
    @media (max-width: 560px) {
      .hero-content { width: calc(100% - 28px); }
      main { width: calc(100% - 28px); }
      .hero-stats { grid-template-columns: 1fr; }
      .results-header { display: block; }
      .status-pill { margin-top: 10px; }
      .platform-chip { width: 100%; justify-content: flex-start; }
      .workflow-strip, .result-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <span class="user-chip">Signed in as __USER_EMAIL__</span>
    <form class="logout-form" method="post" action="/api/auth/logout"><button type="submit">Sign out</button></form>
  </div>
  <header class="hero">
    <div class="hero-content">
      <div>
        <div class="eyebrow">Resume-first daily automation</div>
        <h1>Job Hunting Agent</h1>
        <p>Upload your resume, connect your LinkedIn and Naukri profiles, score ATS readiness, find fresh roles, and prepare recruiter-ready applications from one workspace.</p>
        <div class="platform-strip" aria-label="Supported job workflow channels">
          <span class="platform-chip"><span class="platform-mark linkedin">in</span> LinkedIn jobs</span>
          <span class="platform-chip"><span class="platform-mark naukri">N</span> Naukri search</span>
          <span class="platform-chip"><span class="platform-mark mail">@</span> Recruiter email</span>
        </div>
      </div>
      <div class="hero-stats" aria-label="Workflow highlights">
        <div class="stat-card"><strong>ATS</strong><span>Resume scoring and suggestions</span></div>
        <div class="stat-card"><strong>2</strong><span>Portal adapters configured</span></div>
        <div class="stat-card"><strong>Daily</strong><span>Scheduled search and draft run</span></div>
      </div>
    </div>
  </header>
  <main>
    <form id="agent-form">
      <fieldset>
        <legend><span class="section-badge">1</span>Resume and Profiles</legend>
        <label for="resume">Resume</label>
        <input id="resume" name="resume" type="file" accept=".pdf,.docx,.txt,.md">
        <p class="muted" id="saved-resume">__RESUME_STATUS__</p>
        <label for="linkedin_profile_url">LinkedIn Profile URL</label>
        <input id="linkedin_profile_url" name="linkedin_profile_url" type="url" value="__LINKEDIN_PROFILE_URL__">
        <label for="naukri_profile_url">Naukri Profile URL</label>
        <input id="naukri_profile_url" name="naukri_profile_url" type="url" value="__NAUKRI_PROFILE_URL__">
      </fieldset>
      <fieldset>
        <legend><span class="section-badge">2</span>Candidate</legend>
        <div class="row">
          <div><label for="name">Name</label><input id="name" name="name" value="__NAME__"></div>
          <div><label for="phone">Phone</label><input id="phone" name="phone" value="__PHONE__"></div>
        </div>
        <label for="email">Email</label>
        <input id="email" name="email" type="email" value="__PROFILE_EMAIL__" readonly>
      </fieldset>
      <fieldset>
        <legend><span class="section-badge">3</span>Search</legend>
        <label for="target_roles">Target Roles</label>
        <textarea id="target_roles" name="target_roles">__TARGET_ROLES__</textarea>
        <label for="locations">Locations</label>
        <textarea id="locations" name="locations">__LOCATIONS__</textarea>
        <label for="skills">Skills</label>
        <textarea id="skills" name="skills">__SKILLS__</textarea>
        <div class="row">
          <div><label for="max_jobs_per_portal">Max Jobs Per Portal</label><input id="max_jobs_per_portal" name="max_jobs_per_portal" type="number" min="1" max="50" value="__MAX_JOBS__"></div>
          <div><label for="application_mode">Application Mode</label><select id="application_mode" name="application_mode">__APPLICATION_OPTIONS__</select></div>
        </div>
      </fieldset>
      <fieldset>
        <legend><span class="section-badge">4</span>Daily Automation</legend>
        <div class="row">
          <div><label for="daily_at">Daily Time</label><input id="daily_at" name="daily_at" type="time" value="__DAILY_AT__"></div>
          <div class="schedule-help">Use Schedule Daily Run to upload this resume and start the timer. The app uses your browser timezone and restores active schedules after server restarts.</div>
        </div>
        <input id="daily_timezone" name="daily_timezone" type="hidden" value="UTC">
      </fieldset>
      <div class="actions">
        <button type="submit">Run Agent</button>
        <button class="secondary" id="schedule-run" type="button">Schedule Daily Run</button>
        <button class="secondary" id="stop-scheduler" type="button">Stop Daily Run</button>
      </div>
      <p class="note">Portal submissions are prepared as drafts or recruiter emails. Authenticated LinkedIn/Naukri application submission needs account-specific browser adapters and user approval.</p>
      <div class="workflow-strip" aria-label="Agent workflow">
        <div class="workflow-card"><div class="workflow-icon">CV</div><strong>Resume</strong><span>ATS signals and profile fit</span></div>
        <div class="workflow-card"><div class="workflow-icon">JP</div><strong>Jobs</strong><span>LinkedIn and Naukri leads</span></div>
        <div class="workflow-card"><div class="workflow-icon">@</div><strong>Drafts</strong><span>Messages ready to copy</span></div>
      </div>
    </form>
    <section class="panel">
      <div class="workspace-header">
        <div class="results-header">
          <div>
            <h2>Run Results</h2>
            <p class="muted">ATS score, role matches, missing keywords, and draft actions appear here.</p>
          </div>
        </div>
        <aside class="scheduler-panel" aria-label="Daily scheduler status">
          <div class="scheduler-panel-head"><h3>Daily Automation</h3><span class="status-pill">Ready</span></div>
          <div id="scheduler-status" class="scheduler-grid"></div>
        </aside>
      </div>
      <div id="summary" class="empty-state">
        <div>
          <div class="empty-visual" aria-hidden="true"></div>
          <strong>No run yet</strong>
          <p class="muted">Upload your resume and run the agent to build your daily job pipeline.</p>
        </div>
      </div>
      <div id="details"></div>
    </section>
  </main>
  <script>
    const form = document.getElementById('agent-form');
    const summary = document.getElementById('summary');
    const details = document.getElementById('details');
    const schedulerStatus = document.getElementById('scheduler-status');
    const statusPill = document.querySelector('.status-pill');
    const timezoneInput = document.getElementById('daily_timezone');
    let activeResult = { generatedAt: '', source: '' };
    function enrichFormData() {
      timezoneInput.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
      const data = new FormData(form);
      data.set('daily_timezone', timezoneInput.value);
      return data;
    }
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      summary.textContent = 'Running ATS scoring, portal search, and application drafting...';
      summary.className = 'muted';
      details.innerHTML = '';
      const data = enrichFormData();
      const response = await fetch('/api/run', { method: 'POST', body: data });
      const payload = await response.json();
      if (!response.ok) {
        summary.textContent = payload.detail || 'Run failed.';
        return;
      }
      render(payload, 'manual');
      refreshDashboard();
    });
    document.getElementById('schedule-run').addEventListener('click', async () => {
      summary.className = 'muted';
      summary.textContent = 'Uploading resume and scheduling the daily agent run...';
      details.innerHTML = '';
      const data = enrichFormData();
      const response = await fetch('/api/scheduler/start', { method: 'POST', body: data });
      const payload = await response.json();
      if (!response.ok) {
        summary.textContent = payload.detail || 'Schedule failed.';
        return;
      }
      renderScheduler(payload.scheduler);
      summary.innerHTML = `<p class="muted">Daily run scheduled. The agent will run at the configured time while this server process is active.</p>`;
      refreshDashboard();
    });
    document.getElementById('stop-scheduler').addEventListener('click', async () => {
      const response = await fetch('/api/scheduler/stop', { method: 'POST' });
      const payload = await response.json();
      summary.className = 'muted';
      summary.textContent = payload.running ? 'Scheduler is still running.' : 'Daily run stopped.';
      renderScheduler(payload);
    });
    async function refreshDashboard() {
      let latestResult = null;
      const response = await fetch('/api/dashboard');
      if (response.ok) {
        const payload = await response.json();
        renderScheduler(payload.scheduler);
        latestResult = newerResult(latestResult, payload.scheduler?.last_result);
        const latestStoredRun = payload.latest_run?.payload;
        latestResult = newerResult(latestResult, latestStoredRun);
      }
      if (shouldRenderResult(latestResult)) {
        render(latestResult, latestResult.trigger || 'manual');
      }
    }
    function newerResult(current, candidate) {
      if (!candidate?.generated_at) return current;
      if (!current?.generated_at) return candidate;
      return candidate.generated_at > current.generated_at ? candidate : current;
    }
    function shouldRenderResult(result) {
      if (!result?.generated_at || result.generated_at === activeResult.generatedAt) return false;
      return !activeResult.generatedAt || result.generated_at > activeResult.generatedAt;
    }
    function renderScheduler(scheduler) {
      const running = scheduler && scheduler.running;
      const error = scheduler && scheduler.last_error;
      statusPill.className = `status-pill ${error ? 'error' : running ? '' : 'off'}`;
      statusPill.textContent = error ? 'Error' : running ? 'Scheduled' : 'Ready';
      schedulerStatus.innerHTML = `
        <div class="scheduler-card"><strong>Scheduler</strong><span>${running ? 'Running' : 'Not running'}</span></div>
        <div class="scheduler-card"><strong>Daily time</strong><span>${escapeHtml(scheduler?.daily_at || 'Not set')}</span></div>
        <div class="scheduler-card"><strong>Timezone</strong><span>${escapeHtml(scheduler?.timezone || timezoneInput.value || 'UTC')}</span></div>
        <div class="scheduler-card"><strong>Next run</strong><span>${escapeHtml(scheduler?.next_run_at || 'Not scheduled')}</span></div>
        <div class="scheduler-card"><strong>Last run</strong><span>${escapeHtml(scheduler?.last_run_at || 'No run yet')}</span></div>
      `;
      if (error) {
        schedulerStatus.innerHTML += `<p class="note">Last scheduled run failed: ${escapeHtml(error)}</p>`;
      }
      if (scheduler?.history?.length) {
        const item = scheduler.history[0];
        schedulerStatus.innerHTML += `<ul class="history-list"><li><strong>Latest ${escapeHtml(item.trigger)} run:</strong> ${escapeHtml(item.finished_at || '')} · ${escapeHtml(item.jobs ?? 'n/a')} jobs</li></ul>`;
      }
    }
    function render(payload, source = 'manual') {
      activeResult = { generatedAt: payload.generated_at || activeResult.generatedAt, source };
      const report = payload.ats_report;
      const appSummary = payload.application_summary || {};
      const resultLabel = source === 'scheduled'
        ? `<p class="muted">Showing latest scheduled run from ${escapeHtml(payload.generated_at || 'the scheduler')}.</p>`
        : '';
      const improvedResumeAction = improvedResumeDownload(payload);
      summary.className = '';
      summary.innerHTML = `
        <span class="metric"><strong>${report.score}</strong><span>/100 ATS</span></span>
        <span class="metric"><strong>${payload.jobs.length}</strong><span>jobs</span></span>
        <span class="metric"><strong>${appSummary.drafted || 0}</strong><span>drafts ready</span></span>
        ${resultLabel}
        <p class="muted">Outputs: ${payload.output_dir}</p>
        <p class="muted">${payload.portal_submission_note}</p>
      `;
      const improvements = report.improvements.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
      const missing = report.missing_keywords.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
      const jobs = payload.jobs.slice(0, 12).map((job) => `<tr><td>${escapeHtml(job.portal)}</td><td>${escapeHtml(job.title)}</td><td>${escapeHtml(job.company)}</td><td><a href="${job.url}" target="_blank" rel="noreferrer">Open</a></td></tr>`).join('');
      const draftTemplate = buildDraftTemplate(payload.applications);
      details.innerHTML = `
        <section class="result-section">
          <h3>Resume Signals</h3>
          ${improvedResumeAction || '<p class="muted">Run the agent to prepare a final ATS-friendly resume download.</p>'}
          <div class="result-grid">
            <div><strong>Resume Improvements</strong><ul class="insight-list">${improvements || '<li>No major improvements found.</li>'}</ul></div>
            <div><strong>Missing Keywords</strong><ul class="insight-list">${missing || '<li>No configured keywords are missing.</li>'}</ul></div>
          </div>
        </section>
        <section class="result-section">
          <h3>Job Leads</h3>
          <div class="table-wrap"><table><thead><tr><th>Portal</th><th>Role</th><th>Company</th><th>Link</th></tr></thead><tbody>${jobs}</tbody></table></div>
        </section>
        <section class="result-section">
          <h3>Reusable Draft Message</h3>
          <div class="draft-grid">${draftTemplate ? draftCard(draftTemplate) : '<p class="muted">No draft message was generated for this run.</p>'}</div>
        </section>
      `;
    }
    function improvedResumeDownload(payload) {
      if (!payload.improved_resume || !payload.run_id) return '';
      return `
        <div class="download-actions">
          <a class="download-button" href="/api/runs/${encodeURIComponent(payload.run_id)}/improved-resume">Download Final ATS Resume</a>
          <span class="muted">Single-column DOCX resume using standard ATS section headings.</span>
        </div>
      `;
    }
    function buildDraftTemplate(applications) {
      const firstDraft = applications.find((item) => item.draft_message);
      if (!firstDraft) return '';
      const company = firstDraft.job.company || '';
      let message = firstDraft.draft_message
        .split('\\n')
        .filter((line) => !line.toLowerCase().startsWith('job link:'))
        .join('\\n')
        .trim();
      if (company) {
        message = message.split(company).join('[Company Name]');
      }
      return message;
    }
    function draftCard(message) {
      return `
        <article class="draft-card">
          <div class="draft-card-header">
            <div>
              <strong>Reusable recruiter message</strong>
              <span>Replace [Company Name] before applying to a selected job.</span>
            </div>
            <div class="draft-actions">
              <button class="copy-draft" type="button">Copy Template</button>
            </div>
          </div>
          <textarea class="draft-message" readonly>${escapeHtml(message)}</textarea>
        </article>
      `;
    }
    document.addEventListener('click', async (event) => {
      const button = event.target.closest('.copy-draft');
      if (!button) return;
      const card = button.closest('.draft-card');
      const textarea = card?.querySelector('.draft-message');
      if (!textarea) return;
      await navigator.clipboard.writeText(textarea.value);
      button.textContent = 'Copied';
      setTimeout(() => { button.textContent = 'Copy'; }, 1600);
    });
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
    }
    refreshDashboard();
    setInterval(refreshDashboard, 15000);
  </script>
</body>
</html>"""
    replacements = {
        "__USER_EMAIL__": user_email,
        "__PROFILE_EMAIL__": profile.get("email") or user_email,
        "__NAME__": profile.get("name", ""),
        "__PHONE__": profile.get("phone", ""),
        "__LINKEDIN_PROFILE_URL__": profile.get("linkedin_profile_url", ""),
        "__NAUKRI_PROFILE_URL__": profile.get("naukri_profile_url", ""),
        "__TARGET_ROLES__": profile.get("target_roles", ""),
        "__LOCATIONS__": profile.get("locations", ""),
        "__SKILLS__": profile.get("skills", ""),
        "__MAX_JOBS__": str(profile.get("max_jobs_per_portal", 10)),
        "__DAILY_AT__": profile.get("daily_at", ""),
        "__RESUME_STATUS__": (
            f"Saved resume available: {profile['resume_name']}. Choose a file only to replace it."
            if profile.get("resume_name")
            else "No resume saved yet. Upload one for your first run."
        ),
        "__APPLICATION_OPTIONS__": (
            '<option value="draft">Draft</option><option value="email" selected>Email when recruiter email exists</option>'
            if profile.get("application_mode") == "email"
            else '<option value="draft" selected>Draft</option><option value="email">Email when recruiter email exists</option>'
        ),
    }
    for token, value in replacements.items():
        page = page.replace(token, _escape_html(value) if token != "__APPLICATION_OPTIONS__" else value)
    return page
